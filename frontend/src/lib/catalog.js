import { useEffect, useState } from 'react'
export const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export function apiUrl(path) { return `${API_ORIGIN}${path}` }
export function useCatalog(path) {
 const [attempt, setAttempt] = useState(0)
 const [state, setState] = useState({ key: '', data: null, error: '' })
 const key = `${path}:${attempt}`
 useEffect(() => {
  const controller = new AbortController()
  fetch(apiUrl(`/api/catalog${path}`), { signal: controller.signal })
   .then(async response => {
    if (!response.ok) {
     const body = await response.json().catch(() => ({}))
     throw new Error(typeof body.detail === 'string' ? body.detail : '商品服务暂时不可用，请稍后重试。')
    }
    return response.json()
   })
   .then(data => { if (!controller.signal.aborted) setState({ key, data, error: '' }) })
   .catch(error => { if (!controller.signal.aborted) setState({ key, data: null, error: error.message === 'Failed to fetch' ? '连接不到商品服务，请确认后端已启动。' : error.message }) })
  return () => controller.abort()
 }, [path, key])
 return { data: state.key === key ? state.data : null, error: state.key === key ? state.error : '', loading: state.key !== key, retry: () => setAttempt(value => value + 1) }
}
export function formatPrice(price) {
 return price ? new Intl.NumberFormat('zh-CN', { style: 'currency', currency: price.currency }).format(Number(price.amount)) : '暂无报价'
}
export function displayName(product) {
 if (product.name !== product.name_original) return product.name
 return product.name.split(' - ').slice(0, 2).join(' · ')
}
export function productQuestion(product) {
 const topic = `我想了解 ${product.name}。商品原文介绍：${product.description_original || product.introduction}。这是一条历史商品资料，请不要把参考价格当成当前售价。`
 return `/chat?product=${product.id}&product_name=${encodeURIComponent(product.name)}&topic=${encodeURIComponent(topic)}`
}
