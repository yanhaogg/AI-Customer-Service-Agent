import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop, statuses } from '../lib/shop'
import { tasksChanged } from '../lib/supportTasks'
import ChatText from './ChatText'

export default function ManualOrderAnalysis({ initialOrderId = '', onCreated }) {
  const { token } = useAuth()
  const [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [selected, setSelected] = useState(initialOrderId)
  const [result, setResult] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const orders = useShop(`/api/admin/orders?${new URLSearchParams({ q: search })}`, {
    keepPrevious: true,
  })
  async function analyze() {
    // 第一步只生成预览；管理员读完分析结果后，再通过 create 确认创建正式待办。
    setBusy(true)
    setError('')
    setResult(null)
    try {
      setResult(
        await shopRequest(token, '/api/admin/support-tasks/preview', {
          method: 'POST',
          body: JSON.stringify({ order_id: Number(selected) }),
        }),
      )
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function create(previewId) {
    // 后端会复核预览有效期与订单事实，过期或订单已变化时需要重新分析。
    setBusy(true)
    setError('')
    try {
      const task = await shopRequest(token, '/api/admin/support-tasks', {
        method: 'POST',
        body: JSON.stringify({ preview_id: previewId }),
      })
      setResult((previous) => ({
        ...previous,
        candidates: previous.candidates.map((item) =>
          item.preview_id === previewId ? { ...item, existing_task_id: task.id } : item,
        ),
      }))
      tasksChanged()
      onCreated(task.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="panel task-detail manual-order-analysis">
      <h2>手动分析订单</h2>
      <p>选择订单并点击分析；查看结果后，点击“确认创建待办”才会加入待办列表。</p>
      <form
        className="management-actions"
        onSubmit={(e) => {
          e.preventDefault()
          setSearch(query.trim())
        }}
      >
        <input
          aria-label="搜索订单编号"
          value={query}
          maxLength={40}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入订单编号筛选，默认显示最近订单"
        />
        <button type="submit" className="secondary" disabled={busy}>
          筛选订单
        </button>
      </form>
      {orders.error && <p className="form-error">{orders.error}</p>}
      <label htmlFor="analysis-order">选择订单</label>
      <div className="management-actions">
        <select
          id="analysis-order"
          value={selected}
          disabled={busy}
          onChange={(e) => {
            setSelected(e.target.value)
            setResult(null)
            setError('')
          }}
        >
          <option value="">请选择订单</option>
          {initialOrderId &&
            !orders.data?.items.some((order) => String(order.id) === String(initialOrderId)) && (
              <option value={initialOrderId}>指定订单 #{initialOrderId}</option>
            )}
          {orders.data?.items.map((order) => (
            <option key={order.id} value={order.id}>
              {order.number} · {statuses[order.status] || order.status}
            </option>
          ))}
        </select>
        <button type="button" disabled={busy || !selected} onClick={analyze}>
          {busy ? '处理中…' : '分析所选订单'}
        </button>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {result && (
        <>
          <p role="status">
            订单 {result.order_number}：{result.message}
          </p>
          {result.candidates.map((item) => (
            <section className="task-analysis" key={item.preview_id}>
              <h3>{item.title}</h3>
              <ChatText text={item.advice.analysis} />
              <ol>
                {item.advice.next_steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
              <h3>建议回复草稿</h3>
              <ChatText text={item.advice.suggested_reply} />
              {item.existing_task_id ? (
                <Link to={`/admin/tasks?task=${item.existing_task_id}`}>
                  该事项已有待办，查看处理记录 →
                </Link>
              ) : (
                <button disabled={busy} type="button" onClick={() => create(item.preview_id)}>
                  确认创建待办
                </button>
              )}
            </section>
          ))}
        </>
      )}
    </section>
  )
}
