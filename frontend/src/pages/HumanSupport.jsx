import StaffThread from '../components/StaffThread'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import UnreadBadge from '../components/UnreadBadge'
import { useUnread } from '../lib/chat'
import { useAuth } from '../auth/useAuth'
import { useShop } from '../lib/shop'

function Inbox() {
  const [params] = useSearchParams(),
    navigate = useNavigate()
  const unread = useUnread(true)
  const [status, setStatus] = useState('all'),
    [page, setPage] = useState(1),
    [unreadOnly, setUnreadOnly] = useState(false)
  const data = useShop(
    `/api/admin/support-sessions?${new URLSearchParams({ status, page: String(page), unread_only: String(unreadOnly) })}`,
    { keepPrevious: true },
  )
  const selected = params.get('session') || data.data?.items[0]?.id
  const refresh = data.retry,
    firstSessionId = data.data?.items[0]?.id
  useEffect(() => {
    if (!params.get('session') && firstSessionId)
      navigate(`/admin/support?session=${firstSessionId}`, { replace: true })
  }, [params, firstSessionId, navigate])
  useEffect(() => {
    const timer = setInterval(refresh, 5000)
    window.addEventListener('chat-read', refresh)
    return () => {
      clearInterval(timer)
      window.removeEventListener('chat-read', refresh)
    }
  }, [refresh])
  return (
    <>
      <p className="page-description">
        查看所有客户与 AI、人工客服的会话；发送回复即可转为人工接待。
      </p>
      <label className="unread-filter">
        <input
          type="checkbox"
          checked={unreadOnly}
          onChange={(e) => {
            setUnreadOnly(e.target.checked)
            setPage(1)
            navigate('/admin/support')
          }}
        />
        只看未读
      </label>
      <div className="tabs">
        {[
          ['all', '全部会话'],
          ['none', 'AI 咨询'],
          ['waiting', '待接待'],
          ['active', '接待中'],
          ['closed', '已结束'],
        ].map(([value, label]) => (
          <button
            className={status === value ? 'selected' : ''}
            key={value}
            onClick={() => {
              setStatus(value)
              setPage(1)
              navigate('/admin/support')
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="chat-layout saved-chat-layout">
        <aside className="panel conversation-sidebar">
          {(data.loading && !data.data) || data.error ? (
            <CatalogStatus {...data} />
          ) : (
            <>
              {data.data.items.map((session) => (
                <button
                  className={`staff-session ${String(selected) === String(session.id) ? 'selected' : ''}`}
                  key={session.id}
                  onClick={() => navigate(`/admin/support?session=${session.id}`)}
                >
                  <strong>
                    {session.title} <UnreadBadge count={unread.sessions[session.id] || 0} />
                  </strong>
                  <small>
                    {session.customer_name} · {new Date(session.updated_at).toLocaleString('zh-CN')}
                  </small>
                </button>
              ))}
              {!data.data.items.length && (
                <p>{unreadOnly ? '当前筛选下没有未读会话。' : '当前没有会话。'}</p>
              )}
              <nav className="pagination">
                <button
                  className="secondary"
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  上一页
                </button>
                <span>
                  {page} / {data.data.total_pages || 1}
                </span>
                <button
                  className="secondary"
                  disabled={page >= data.data.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                </button>
              </nav>
            </>
          )}
        </aside>
        {selected ? (
          <StaffThread key={selected} id={selected} onChange={data.retry} />
        ) : (
          <section className="panel shop-empty">请选择一个人工会话。</section>
        )}
      </div>
    </>
  )
}
export default function HumanSupport() {
  const auth = useAuth()
  return (
    <ShopShell title="客服工作台" admin>
      {auth.isAdmin && <Inbox />}
    </ShopShell>
  )
}
