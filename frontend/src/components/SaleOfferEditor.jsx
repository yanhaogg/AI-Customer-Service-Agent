import { useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop } from '../lib/shop'
import CatalogStatus from './CatalogStatus'

function OfferForm({ productId, offer, onClose, onSaved }) {
  const { token } = useAuth()
  const [form, setForm] = useState(
    offer || {
      price: '',
      currency: 'CNY',
      stock: 0,
      is_active: false,
      updated_at: null,
    },
  )
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await shopRequest(token, `/api/admin/offers/${productId}`, {
        method: 'PUT',
        body: JSON.stringify({ ...form, stock: Number(form.stock) }),
      })
      onSaved()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={save}>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <fieldset disabled={busy}>
        <p>演示售价独立于历史参考价；库存为可供下单数量，待支付订单已占用的数量不包含在内。</p>
        <div className="product-form-grid">
          <label>
            演示售价
            <input
              required
              type="number"
              min="0.01"
              step="0.01"
              max="9999999999.99"
              value={form.price}
              onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
            />
          </label>
          <label>
            币种
            <select
              value={form.currency}
              onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
            >
              {['CNY', 'USD', 'EUR', 'GBP', 'JPY', 'HKD'].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            可售库存
            <input
              required
              type="number"
              min="0"
              step="1"
              max="1000000"
              value={form.stock}
              onChange={(e) => setForm((f) => ({ ...f, stock: e.target.value }))}
            />
          </label>
        </div>
        <label className="check-line">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
          />
          允许购买（上架）
        </label>
        <div className="management-actions">
          <button>{busy ? '保存中…' : '保存销售设置'}</button>
          <button type="button" className="secondary" onClick={onClose}>
            取消
          </button>
        </div>
      </fieldset>
    </form>
  )
}
export default function SaleOfferEditor({ productId, onClose, onSaved }) {
  const data = useShop(`/api/admin/offers/${productId}`)
  return (
    <section className="panel product-editor">
      <h2>销售设置 · 商品 #{productId}</h2>
      {data.loading || data.error ? (
        <CatalogStatus {...data} />
      ) : (
        <OfferForm
          key={`${productId}:${data.data.offer?.updated_at || 'new'}`}
          productId={productId}
          offer={data.data.offer}
          onClose={onClose}
          onSaved={onSaved}
        />
      )}
    </section>
  )
}
