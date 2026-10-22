import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import CatalogStatus from './CatalogStatus'
import ChatText from './ChatText'
import AgentCollaboration from './AgentCollaboration'
import StaffAssistant from './StaffAssistant'
import { useConversationRead } from '../lib/chat'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop } from '../lib/shop'

// 单个会话：消息加载、人工接待、历史分页与回复。
export default function StaffThread({ id, onChange }) {
  // 单个会话独立维护草稿和请求编号；父组件切换 key 后重新挂载，避免把草稿带到其他客户。
  const { token } = useAuth(),
    thread = useShop(`/api/admin/support-sessions/${id}`, {
      keepPrevious: true,
    })
  const [draft, setDraft] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [older, setOlder] = useState([]),
    [more, setMore] = useState(null)
  useConversationRead(`/api/admin/support-sessions/${id}`, thread.data)
  const key = useRef(crypto.randomUUID()),
    messageLog = useRef(null),
    replyBox = useRef(null),
    retry = thread.retry
  const latestMessageId = thread.data?.items.at(-1)?.id
  useEffect(() => {
    messageLog.current?.scrollTo({
      top: messageLog.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [latestMessageId])
  useEffect(() => {
    const timer = setInterval(retry, 4000)
    return () => clearInterval(timer)
  }, [retry])
  function applySuggestion(text) {
    setDraft(text)
    key.current = crypto.randomUUID()
    replyBox.current?.focus()
    replyBox.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  async function send(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await shopRequest(token, `/api/admin/support-sessions/${id}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: draft, request_key: key.current }),
      })
      setDraft('')
      key.current = crypto.randomUUID()
      thread.retry()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function close() {
    setBusy(true)
    setError('')
    try {
      await shopRequest(token, `/api/admin/support-sessions/${id}/close`, {
        method: 'POST',
      })
      thread.retry()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function earlier() {
    const first = older[0]?.id || thread.data?.items[0]?.id
    if (!first) return
    try {
      const result = await shopRequest(
        token,
        `/api/admin/support-sessions/${id}?before_id=${first}`,
      )
      setOlder((entries) => [...result.items, ...entries])
      setMore(result.has_more)
    } catch (err) {
      setError(err.message)
    }
  }
  if (thread.error || (!thread.data && thread.loading)) return <CatalogStatus {...thread} />
  if (!thread.data) return null
  const session = thread.data.session,
    messages = [...older, ...thread.data.items].filter(
      (m, index, all) => all.findIndex((x) => x.id === m.id) === index,
    )
  return (
    <section className="panel chat-panel">
      <div className="chat-header">
        <div>
          <strong>{session.title}</strong>
          <p>
            {session.context_name || '日常商品咨询'} ·{' '}
            {session.human_status === 'none'
              ? 'AI 咨询'
              : session.human_status === 'waiting'
                ? '待接待'
                : session.human_status === 'active'
                  ? '人工接待中'
                  : '已结束'}
          </p>
          {session.order_id && (
            <Link to={`/admin/orders?q=${encodeURIComponent(session.context_name || '')}`}>
              查看关联订单与售后 →
            </Link>
          )}
        </div>
        <button
          className="secondary"
          disabled={busy || !['waiting', 'active'].includes(session.human_status)}
          onClick={close}
        >
          结束接待
        </button>
      </div>
      <section className="linked-support-tasks">
        <Link to="/admin/tasks">客服待办 →</Link>
        {thread.data.support_tasks?.map((task) => (
          <Link key={task.id} to={`/admin/tasks?task=${task.id}`}>
            {task.title} · {task.status === 'in_progress' ? '处理中' : '待认领'}
          </Link>
        ))}
      </section>
      <StaffAssistant
        id={id}
        version={thread.data.assist_version}
        onUse={applySuggestion}
        disabled={busy || session.human_status === 'closed'}
        hasDraft={!!draft.trim()}
      />
      <div ref={messageLog} className="chat-messages" role="log">
        {(more ?? thread.data.has_more) && (
          <button className="secondary" onClick={earlier}>
            更早消息
          </button>
        )}
        {messages.map((m) => (
          <div
            className={`message ${m.is_mine ? 'outgoing' : 'incoming'} ${m.role === 'human_agent' ? 'human-message' : ''}`}
            key={m.id}
          >
            <span>
              {m.is_mine
                ? '我'
                : m.role === 'user'
                  ? '用户'
                  : m.role === 'human_agent'
                    ? '客服'
                    : 'AI'}
            </span>
            <div className="saved-message">
              <ChatText text={m.content || '正在处理…'} />
              <AgentCollaboration metadata={m.agent_metadata} />
              <small>{new Date(m.created_at).toLocaleString('zh-CN')}</small>
            </div>
          </div>
        ))}
      </div>
      <form className="chat-compose" onSubmit={send}>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <label htmlFor="staff-reply">人工客服回复</label>
        <textarea
          ref={replyBox}
          id="staff-reply"
          required
          maxLength={10000}
          disabled={busy || session.human_status === 'closed'}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            key.current = crypto.randomUUID()
          }}
          rows={3}
        />
        <div>
          <small>发送回复将接管此会话并暂停 AI 自动回复。退款请在关联订单中按流程审核。</small>
          <button disabled={busy || !draft.trim() || session.human_status === 'closed'}>
            发送并接待
          </button>
        </div>
      </form>
    </section>
  )
}
