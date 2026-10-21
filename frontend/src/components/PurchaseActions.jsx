import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { money, shopRequest } from '../lib/shop'

export default function PurchaseActions({ product, compact = false }) {
  const auth = useAuth(),
    navigate = useNavigate()
  const [quantity, setQuantity] = useState(1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [added, setAdded] = useState(false)
  const offer = product.offer,
    available = offer?.is_active && offer.stock > 0
  const checkout = `/checkout?product=${product.id}&quantity=${quantity}`
  async function add() {
    if (!auth.user) {
      navigate(`/login?redirect=${encodeURIComponent(`/products/${product.id}`)}`)
      return
    }
    setBusy(true)
    setError('')
    setAdded(false)
    try {
      await shopRequest(auth.token, '/api/shop/cart', {
        method: 'POST',
        body: JSON.stringify({ product_id: product.id, quantity }),
      })
      setAdded(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  if (compact)
    return (
      <div className="quick-purchase">
        <div className="management-actions">
          <Link
            className="button"
            aria-disabled={!available}
            to={
              available
                ? auth.user
                  ? checkout
                  : `/login?redirect=${encodeURIComponent(checkout)}`
                : `/products/${product.id}`
            }
          >
            {available ? '立即购买' : '查看商品'}
          </Link>
          <button className="secondary" disabled={busy || !available} onClick={add}>
            加入购物车
          </button>
        </div>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        {added && <Link to="/cart">已加入 · 去结算 →</Link>}
      </div>
    )
  return (
    <section className="purchase-box">
      <strong className="purchase-price">
        {offer?.amount ? money(offer.amount, offer.currency) : '暂未设置售价'}
      </strong>
      <small>演示售价 · 库存 {offer?.stock || 0} · 模拟支付</small>
      {available ? (
        <>
          <label>
            购买数量{' '}
            <input
              aria-label="购买数量"
              type="number"
              min="1"
              max={Math.min(99, offer.stock)}
              value={quantity}
              onChange={(e) =>
                setQuantity(
                  Math.max(1, Math.min(99, offer.stock, Math.trunc(Number(e.target.value)) || 1)),
                )
              }
            />
          </label>
          <div className="management-actions">
            <Link
              className="button"
              to={auth.user ? checkout : `/login?redirect=${encodeURIComponent(checkout)}`}
            >
              立即购买
            </Link>
            <button className="secondary" disabled={busy} onClick={add}>
              {busy ? '加入中…' : '加入购物车'}
            </button>
          </div>
        </>
      ) : (
        <p>商品暂不可购买，请稍后再来。</p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {added && (
        <p role="status" className="success-note">
          已加入购物车。<Link to="/cart">去购物车结算 →</Link>
        </p>
      )}
      <p className="detail-notice">
        当前为演示商城，商品价格与库存均用于测试，不提供真实支付和配送。
      </p>
    </section>
  )
}
