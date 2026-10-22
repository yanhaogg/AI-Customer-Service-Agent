import { useEffect, useRef } from 'react'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop } from './shop'

export function useUnread(admin = false, enabled = true) {
  // 轮询只刷新提醒，不会标记已读；用户与管理员分别调用各自有权限的接口。
  const result = useShop(
    enabled ? (admin ? '/api/admin/support-sessions/unread' : '/api/activity/unread') : null,
    { keepPrevious: true },
  )
  const refresh = result.retry
  useEffect(() => {
    if (!enabled) return
    const timer = setInterval(refresh, 5000)
    window.addEventListener('chat-read', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      clearInterval(timer)
      window.removeEventListener('chat-read', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [enabled, refresh])
  return result.data || { total: 0, sessions: {} }
}

export function useConversationRead(path, data) {
  // 只确认本次已加载消息的时间水位；页面可见且窗口获得焦点时才认为用户正在阅读。
  const { token } = useAuth(),
    last = useRef('')
  const watermark = data?.read_through
  useEffect(() => {
    if (!path || !watermark || !token) return
    let cancelled = false,
      inFlight = false
    const identity = `${token}:${path}:${watermark}`
    async function read() {
      if (
        cancelled ||
        inFlight ||
        document.visibilityState !== 'visible' ||
        !document.hasFocus() ||
        last.current === identity
      )
        return
      inFlight = true
      try {
        await shopRequest(token, `${path}/read`, {
          method: 'POST',
          body: JSON.stringify({ read_through: watermark }),
        })
        if (!cancelled) {
          last.current = identity
          window.dispatchEvent(new Event('chat-read'))
        }
      } catch {
        /* 确认失败时保留未读，页面可见期间继续重试，避免消息被误清零。 */
      } finally {
        inFlight = false
      }
    }
    read()
    const timer = setInterval(read, 5000)
    window.addEventListener('focus', read)
    document.addEventListener('visibilitychange', read)
    return () => {
      cancelled = true
      clearInterval(timer)
      window.removeEventListener('focus', read)
      document.removeEventListener('visibilitychange', read)
    }
  }, [token, path, watermark])
}
