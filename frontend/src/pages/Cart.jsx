import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogImage from '../components/CatalogImage'
import CatalogStatus from '../components/CatalogStatus'
import { useAuth } from '../auth/useAuth'
import { money, shopRequest, useShop } from '../lib/shop'

export default function Cart() {
  const auth = useAuth(),
    cart = useShop('/api/shop/cart'),
    navigate = useNavigate()
  const [selected, setSelected] = useState([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  const items = cart.data?.items || [],
    valid = items.filter((i) => i.available && i.product.offer.stock >= i.quantity)
  const chosen = valid.filter((i) => selected.includes(i.id)),
    totals = {}
  chosen.forEach((i) => {
    const o = i.product.offer
    totals[o.currency] = (totals[o.currency] || 0) + Number(o.amount) * i.quantity
  })
  async function update(item, quantity) {
    if (quantity < 1 || quantity > 99) return
    setBusy(true)
    setError('')
    try {
      await shopRequest(auth.token, `/api/shop/cart/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ quantity }),
      })
      cart.retry()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function remove(id) {
    setBusy(true)
    setError('')
    try {
      await shopRequest(auth.token, `/api/shop/cart/${id}`, {
        method: 'DELETE',
      })
      setSelected((s) => s.filter((x) => x !== id))
      cart.retry()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <ShopShell title="购物车">
      <p className="demo-note">
        演示商城：使用演示售价与库存，结算不会真实扣款。不同币种需分别下单。
      </p>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {cart.loading || cart.error ? (
        <CatalogStatus {...cart} />
      ) : !items.length ? (
        <section className="panel shop-empty">
          <h2>购物车还是空的</h2>
          <Link className="button" to="/products">
            去逛商品
          </Link>
        </section>
      ) : (
        <>
          <section className="panel shop-panel">
            <label className="check-line">
              <input
                type="checkbox"
                checked={valid.length > 0 && chosen.length === valid.length}
                onChange={(e) => setSelected(e.target.checked ? valid.map((i) => i.id) : [])}
              />
              全选可购买商品
            </label>
            {items.map((item) => {
              const p = item.product,
                o = p?.offer,
                canChoose = valid.some((i) => i.id === item.id)
              return (
                <article className="cart-row" key={item.id}>
                  <input
                    type="checkbox"
                    aria-label={`选择 ${p?.name || '已删除商品'}`}
                    disabled={!canChoose || busy}
                    checked={canChoose && selected.includes(item.id)}
                    onChange={(e) =>
                      setSelected((s) =>
                        e.target.checked ? [...s, item.id] : s.filter((id) => id !== item.id),
                      )
                    }
                  />
                  <CatalogImage product={p || { name: '商品已删除' }} />
                  <div className="cart-description">
                    <Link to={`/products/${item.product_id}`}>{p?.name || '商品已删除'}</Link>
                    <small>
                      {o?.amount ? money(o.amount, o.currency) : '暂无售价'} · 库存 {o?.stock || 0}
                    </small>
                    {!canChoose && (
                      <small className="form-error">已下架或库存不足，请调整数量或移除</small>
                    )}
                  </div>
                  <div className="quantity-control">
                    <button
                      className="secondary"
                      disabled={busy || item.quantity <= 1}
                      onClick={() => update(item, item.quantity - 1)}
                    >
                      −
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      className="secondary"
                      disabled={busy || item.quantity >= 99 || !item.available}
                      onClick={() => update(item, item.quantity + 1)}
                    >
                      ＋
                    </button>
                  </div>
                  <button className="danger-button" disabled={busy} onClick={() => remove(item.id)}>
                    移除
                  </button>
                </article>
              )
            })}
          </section>
          <section className="panel checkout-bar">
            <span>已选择 {chosen.length} 款商品</span>
            <strong>
              {Object.entries(totals)
                .map(([currency, total]) => money(total, currency))
                .join(' + ') || '请选择商品'}
            </strong>
            <button
              disabled={busy || !chosen.length || Object.keys(totals).length > 1}
              onClick={() => navigate(`/checkout?cart=${chosen.map((i) => i.id).join(',')}`)}
            >
              结算所选商品 →
            </button>
          </section>
          {Object.keys(totals).length > 1 && (
            <p role="alert" className="form-error">
              请选择相同币种商品进行结算。
            </p>
          )}
        </>
      )}
    </ShopShell>
  )
}
