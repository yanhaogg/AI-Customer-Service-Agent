import { useEffect } from 'react'
import { useShop } from './shop'

export const taskStatuses = {
  pending: '待认领',
  in_progress: '处理中',
  resolved: '已完成',
  dismissed: '已忽略',
}
export const taskKinds = {
  shipping_overdue: '超时未发货',
  receipt_overdue: '长期未确认收货',
  refund_overdue: '退款审核超时',
}
export function tasksChanged() {
  window.dispatchEvent(new Event('support-tasks-changed'))
}
export function useTaskSummary(enabled = true) {
  const result = useShop(enabled ? '/api/admin/support-tasks/summary' : null, {
      keepPrevious: true,
    }),
    refresh = result.retry
  useEffect(() => {
    if (!enabled) return
    const timer = setInterval(refresh, 15000)
    window.addEventListener('support-tasks-changed', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      clearInterval(timer)
      window.removeEventListener('support-tasks-changed', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [enabled, refresh])
  return result
}
