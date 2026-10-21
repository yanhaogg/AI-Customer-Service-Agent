import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import ChatText from '../components/ChatText'
import UnreadBadge from '../components/UnreadBadge'
import AgentCollaboration from '../components/AgentCollaboration'
import { useUnread, useConversationRead } from '../lib/chat'

const toolLabels = {
  list_product_categories: '商品分类',
  search_products: '商品搜索',
  get_product_details: '商品详情',
  list_my_orders: '本人订单',
  get_my_order_details: '订单详情',
  get_my_browsing_history: '最近浏览',
  search_my_chat_history: '聊天历史',
  get_refund_policy: '退款政策',
}
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop } from '../lib/shop'

function ChatWorkspace() {
  const auth = useAuth(),
    navigate = useNavigate(),
    [params] = useSearchParams()
  const sessionId = params.get('session')
  const [draft, setDraft] = useState(() => (params.get('topic') || '').slice(0, 10000))
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [page, setPage] = useState(1),
    [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [deleting, setDeleting] = useState(null)
  const [older, setOlder] = useState([]),
    [olderMore, setOlderMore] = useState(null),
    [loadingOlder, setLoadingOlder] = useState(false)
  const request = useRef(null),
    bottom = useRef(null)
  const agentStatus = useShop('/api/activity/agent-status')
  const sessions = useShop(
    `/api/activity/sessions?${new URLSearchParams({ page: String(page), q: search })}`,
  )
  const conversation = useShop(
    sessionId ? `/api/activity/sessions/${encodeURIComponent(sessionId)}` : null,
    { keepPrevious: true },
  )
  const unread = useUnread()
  useConversationRead(
    sessionId ? `/api/activity/sessions/${encodeURIComponent(sessionId)}` : null,
    conversation.data,
  )
  const records = [...older, ...(conversation.data?.items || [])].filter(
    (message, index, array) => array.findIndex((m) => m.id === message.id) === index,
  )
  const humanStatus = conversation.data?.session.human_status
  const humanActive = ['waiting', 'active'].includes(humanStatus)
  const pending = records.some((m) => m.status === 'pending')
  const latestMessageId = records.at(-1)?.id
  const refreshConversation = conversation.retry
  useEffect(() => {
    if (!sessionId) return
    const interval = setInterval(refreshConversation, 2500)
    return () => clearInterval(interval)
  }, [sessionId, refreshConversation])
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [latestMessageId, busy])

  function switchSession(id) {
    if (busy) return
    setDraft('')
    setError('')
    setOlder([])
    setOlderMore(null)
    request.current = null
    navigate(id ? `/chat?session=${id}` : '/chat')
  }
  async function send(event, retryMessage = null) {
    event?.preventDefault()
    if (busy || pending) return
    const content = retryMessage?.content || draft.trim()
    if (!content) return
    setBusy(true)
    setError('')
    let target = sessionId
    try {
      if (!target) {
        const body = { title: content.slice(0, 80) }
        if (params.get('product')) body.product_id = Number(params.get('product'))
        if (params.get('order')) body.order_number = params.get('order')
        const session = await shopRequest(auth.token, '/api/activity/sessions', {
          method: 'POST',
          body: JSON.stringify(body),
        })
        target = String(session.id)
      }
      if (retryMessage) request.current = { content, request_key: retryMessage.request_key }
      else if (request.current?.content !== content)
        request.current = { content, request_key: crypto.randomUUID() }
      await shopRequest(auth.token, `/api/activity/sessions/${target}/messages`, {
        method: 'POST',
        body: JSON.stringify(request.current),
      })
      setDraft('')
      request.current = null
    } catch (err) {
      setError(err.message)
    } finally {
      if (target && target !== sessionId) navigate(`/chat?session=${target}`, { replace: true })
      setBusy(false)
      conversation.retry()
      sessions.retry()
    }
  }
  async function remove() {
    setBusy(true)
    setError('')
    try {
      await shopRequest(auth.token, `/api/activity/sessions/${deleting.id}`, {
        method: 'DELETE',
      })
      if (String(deleting.id) === sessionId) {
        navigate('/chat')
        setDraft('')
        setOlder([])
        setOlderMore(null)
      }
      setDeleting(null)
      setPage(1)
      sessions.retry()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function handoff() {
    if (!sessionId) return
    setBusy(true)
    setError('')
    try {
      await shopRequest(auth.token, `/api/activity/sessions/${sessionId}/handoff`, {
        method: 'POST',
      })
      conversation.retry()
      sessions.retry()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function loadOlder() {
    const first = records[0]?.id
    if (!first) return
    setLoadingOlder(true)
    setError('')
    try {
      const data = await shopRequest(
        auth.token,
        `/api/activity/sessions/${sessionId}?before_id=${first}`,
      )
      setOlder((previous) => [...data.items, ...previous])
      setOlderMore(data.has_more)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingOlder(false)
    }
  }
  return (
    <>
      <p className="page-description">聊天记录会保存到当前账号，可随时恢复咨询。</p>
      <p className="demo-note">
        支持查询商品、本人订单与最近浏览，并结合聊天历史回答。购买与支付仍为演示流程。
      </p>
      {deleting && (
        <section
          className="panel history-confirm"
          role="alertdialog"
          aria-labelledby="delete-session-title"
        >
          <h2 id="delete-session-title">删除会话“{deleting.title}”？</h2>
          <p>会话及其中的聊天消息都会删除。</p>
          <div className="management-actions">
            <button className="danger-button" disabled={busy} onClick={remove}>
              确认删除
            </button>
            <button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>
              取消
            </button>
          </div>
        </section>
      )}
      <div className="chat-layout saved-chat-layout">
        <aside className="panel conversation-sidebar">
          <div className="shop-toolbar">
            <h2>历史会话</h2>
            <button className="secondary" disabled={busy} onClick={() => switchSession(null)}>
              ＋ 新会话
            </button>
          </div>
          <form
            className="conversation-search"
            onSubmit={(e) => {
              e.preventDefault()
              setSearch(query.trim())
              setPage(1)
            }}
          >
            <input
              aria-label="搜索历史会话"
              maxLength={100}
              placeholder="搜索会话标题"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button className="secondary">搜索</button>
          </form>
          {sessions.loading || sessions.error ? (
            <CatalogStatus {...sessions} />
          ) : (
            <>
              <div className="conversation-list">
                {sessions.data?.items.map((session) => (
                  <div
                    className={`conversation-item ${String(session.id) === sessionId ? 'selected' : ''}`}
                    key={session.id}
                  >
                    <button
                      className="conversation-open"
                      disabled={busy}
                      onClick={() => switchSession(session.id)}
                    >
                      <strong>
                        {session.title} <UnreadBadge count={unread.sessions[session.id] || 0} />
                      </strong>
                      <small>{new Date(session.updated_at).toLocaleString('zh-CN')}</small>
                    </button>
                    <button
                      className="conversation-delete"
                      disabled={busy}
                      aria-label={`删除会话 ${session.title}`}
                      onClick={() => setDeleting(session)}
                    >
                      ×
                    </button>
                  </div>
                ))}
                {sessions.data?.total === 0 && <p>还没有历史会话。</p>}
              </div>
              <nav className="pagination" aria-label="会话分页">
                <button
                  className="secondary"
                  disabled={page === 1 || busy}
                  onClick={() => setPage((p) => p - 1)}
                >
                  上一页
                </button>
                <span>
                  {page} / {sessions.data?.total_pages || 1}
                </span>
                <button
                  className="secondary"
                  disabled={!sessions.data || page >= sessions.data.total_pages || busy}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                </button>
              </nav>
            </>
          )}
        </aside>
        <section className="panel chat-panel">
          <div className="chat-header">
            <div>
              <strong>{conversation.data?.session.title || 'ServAI 智能客服'}</strong>
              <p>
                {conversation.data?.session.context_name ||
                  (params.get('product_name')
                    ? `商品咨询：${params.get('product_name')}`
                    : params.get('order')
                      ? `订单咨询：${params.get('order')}`
                      : '选择历史会话或开始新的咨询')}
              </p>
            </div>
            <div className="management-actions">
              {conversation.data?.session.order_id && (
                <>
                  <a href={`/orders/${conversation.data.session.order_id}`}>关联订单 ↗</a>
                  <button className="secondary" disabled={busy || humanActive} onClick={handoff}>
                    {humanStatus === 'waiting'
                      ? '等待人工客服'
                      : humanStatus === 'active'
                        ? '人工接待中'
                        : '转人工客服'}
                  </button>
                </>
              )}
              <span className="pill">
                {humanActive
                  ? '人工服务'
                  : agentStatus.data?.configured
                    ? agentStatus.data.model
                    : '模型待配置'}
              </span>
            </div>
          </div>
          <div className="chat-messages" role="log" aria-live="polite">
            {sessionId && conversation.error ? (
              <CatalogStatus {...conversation} />
            ) : (
              <>
                {sessionId && conversation.loading && !records.length && <CatalogStatus loading />}
                {!sessionId && (
                  <div className="message assistant">
                    <span>✧</span>
                    <p>你好，欢迎来到 ServAI！发送消息即可开始一个保存到账号的会话。</p>
                  </div>
                )}
                {(olderMore ?? conversation.data?.has_more) && (
                  <button
                    className="secondary earlier-messages"
                    disabled={loadingOlder || busy}
                    onClick={loadOlder}
                  >
                    {loadingOlder ? '加载中…' : '查看更早的聊天记录'}
                  </button>
                )}
                {records.map((m, index) => (
                  <div
                    className={`message ${m.role === 'user' ? 'outgoing' : 'incoming'} ${m.role === 'human_agent' ? 'human-message' : ''}`}
                    key={m.id}
                  >
                    <span>
                      {m.role === 'user' ? '我' : m.role === 'human_agent' ? '客服' : '✧'}
                    </span>
                    <div className="saved-message">
                      {m.role !== 'user' ? (
                        <ChatText
                          text={m.status === 'pending' ? '正在查询并组织回复…' : m.content}
                        />
                      ) : (
                        <p>{m.content}</p>
                      )}
                      <AgentCollaboration metadata={m.agent_metadata} />
                      {m.agent_metadata?.tools?.length > 0 && (
                        <details className="chat-tool-summary">
                          <summary>本次查询依据</summary>
                          <ul>
                            {m.agent_metadata.tools.map((tool, index) => (
                              <li key={index}>
                                {toolLabels[tool.name] || '查询工具'} ·{' '}
                                {tool.status === 'ok'
                                  ? '已查询'
                                  : tool.status === 'not_found'
                                    ? '未找到记录'
                                    : '未完成'}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                      <small>{new Date(m.created_at).toLocaleString('zh-CN')}</small>
                      {m.status === 'failed' && (
                        <button
                          className="secondary"
                          disabled={busy || pending}
                          onClick={() =>
                            send(
                              null,
                              records
                                .slice(0, index)
                                .findLast(
                                  (item) =>
                                    item.role === 'user' && item.request_key === m.request_key,
                                ),
                            )
                          }
                        >
                          重试回复
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {busy && (
                  <p role="status" className="muted">
                    正在保存消息、查询数据并生成回复…
                  </p>
                )}
                <div ref={bottom} />
              </>
            )}
          </div>
          <form className="chat-compose" onSubmit={send}>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <label className="sr-only" htmlFor="message">
              咨询问题
            </label>
            <textarea
              id="message"
              maxLength={10000}
              disabled={busy || pending}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="输入你的问题，聊天记录将自动保存"
              rows={3}
            />
            <div>
              <small>回复结合查询结果；下单、支付或售后操作请在对应页面完成。</small>
              <button
                disabled={
                  busy ||
                  pending ||
                  !draft.trim() ||
                  (sessionId && (!conversation.data || !!conversation.error))
                }
              >
                {busy || pending ? '处理中…' : '发送消息 ↑'}
              </button>
            </div>
          </form>
        </section>
      </div>
    </>
  )
}
export default function SavedChat() {
  const auth = useAuth(),
    [params] = useSearchParams()
  return (
    <ShopShell title="你的专属客服">
      {auth.user && (
        <ChatWorkspace
          key={`${auth.user.id}:${params.get('session') || 'new'}:${params.get('product') || ''}:${params.get('order') || ''}`}
        />
      )}
    </ShopShell>
  )
}
