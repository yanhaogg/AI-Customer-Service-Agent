import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import CatalogImage from '../components/CatalogImage'
import AddressForm from '../components/AddressForm'
import { useAuth } from '../auth/useAuth'
import { money, shopRequest, useShop } from '../lib/shop'

function CheckoutContent() {
  const auth = useAuth(),
    [params] = useSearchParams(),
    navigate = useNavigate()
  const cart = useShop(params.has('cart') ? '/api/shop/cart' : null),
    addresses = useShop('/api/shop/addresses')
  const [addressId, setAddressId] = useState(''),
    [adding, setAdding] = useState(false),
    [note, setNote] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [quote, setQuote] = useState(null),
    [quoteError, setQuoteError] = useState(''),
    [attempt, setAttempt] = useState(0),
    [requestKey, setRequestKey] = useState(() => crypto.randomUUID())
  const cartIds = params.has('cart') ? params.get('cart').split(',').map(Number) : []
  const chosen = cart.data?.items.filter((i) => cartIds.includes(i.id)) || []
  const items = params.has('cart')
    ? chosen.map((i) => ({ product_id: i.product_id, quantity: i.quantity }))
    : [
        {
          product_id: Number(params.get('product')),
          quantity: Number(params.get('quantity') || 1),
        },
      ]
  const selectionKey = JSON.stringify(items),
    ready =
      !params.has('cart') || (cart.data && chosen.length === cartIds.length && chosen.length > 0)
  const key = `${selectionKey}:${attempt}`
  useEffect(() => {
    if (!ready) return
    const controller = new AbortController()
    shopRequest(auth.token, '/api/shop/checkout/preview', {
      method: 'POST',
      body: JSON.stringify({ items: JSON.parse(selectionKey) }),
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) {
          setQuote({ key, data })
          setQuoteError('')
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setQuote({ key, data: null })
          setQuoteError(err.message)
        }
      })
    return () => controller.abort()
  }, [auth.token, selectionKey, ready, key])
  const data = quote?.key === key ? quote.data : null
  const selectedAddress = addressId || String(addresses.data?.items[0]?.id || '')
  async function submit() {
    setBusy(true)
    setError('')
    try {
      const order = await shopRequest(auth.token, '/api/shop/orders', {
        method: 'POST',
        body: JSON.stringify({
          items: data.items.map((i) => ({
            product_id: i.product_id,
            quantity: i.quantity,
            expected_price: i.unit_price,
            currency: data.currency,
          })),
          address_id: Number(selectedAddress),
          cart_item_ids: cartIds,
          request_key: requestKey,
          note,
        }),
      })
      navigate(`/orders/${order.id}`, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <p className="demo-note">
        演示订单 · 模拟支付 · 运费为 0。提交后保留库存 30 分钟，请在订单页完成模拟支付。
      </p>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {cart.error && <CatalogStatus {...cart} />}{' '}
      {!ready && !cart.loading && (
        <p role="alert" className="form-error">
          所选购物车条目已变化，请<Link to="/cart">返回购物车</Link>重新选择。
        </p>
      )}
      <section className="panel shop-panel">
        <div className="shop-toolbar">
          <h2>收货信息</h2>
          <button className="secondary" disabled={busy} onClick={() => setAdding(true)}>
            新增地址
          </button>
        </div>
        {addresses.loading || addresses.error ? (
          <CatalogStatus {...addresses} />
        ) : (
          addresses.data?.items.map((a) => (
            <label
              className={`address-choice ${String(a.id) === selectedAddress ? 'selected' : ''}`}
              key={a.id}
            >
              <input
                type="radio"
                name="shipping-address"
                disabled={busy}
                checked={String(a.id) === selectedAddress}
                onChange={() => {
                  setAddressId(String(a.id))
                  setRequestKey(crypto.randomUUID())
                }}
              />
              <span>
                <strong>
                  {a.recipient} · {a.phone}
                </strong>
                <small>
                  {a.region} {a.detail} {a.postal_code}
                </small>
              </span>
              {a.is_default && <span className="pill">默认</span>}
            </label>
          ))
        )}
        {addresses.data?.items.length === 0 && <p>请先新增收货地址。</p>}
        {adding && (
          <AddressForm
            onCancel={() => setAdding(false)}
            onSaved={(a) => {
              setAddressId(String(a.id))
              setRequestKey(crypto.randomUUID())
              setAdding(false)
              addresses.retry()
            }}
          />
        )}
      </section>
      <section className="panel shop-panel">
        <h2>确认商品</h2>
        {quoteError && (
          <p role="alert" className="form-error">
            {quoteError}
          </p>
        )}
        {!data ? (
          quoteError ? (
            <button
              className="secondary"
              onClick={() => {
                setAttempt((n) => n + 1)
                setRequestKey(crypto.randomUUID())
              }}
            >
              重新核价
            </button>
          ) : (
            <CatalogStatus loading />
          )
        ) : (
          <>
            {data.items.map((i) => (
              <article className="cart-row" key={i.product_id}>
                <CatalogImage product={i} />
                <div className="cart-description">
                  <strong>{i.name}</strong>
                  <small>
                    {money(i.unit_price, data.currency)} × {i.quantity}
                  </small>
                </div>
                <strong>{money(i.subtotal, data.currency)}</strong>
              </article>
            ))}
            <label className="checkout-note">
              订单备注
              <textarea
                disabled={busy}
                maxLength={500}
                rows={2}
                value={note}
                onChange={(e) => {
                  setNote(e.target.value)
                  setRequestKey(crypto.randomUUID())
                }}
                placeholder="可填写配送备注，最多 500 字"
              />
            </label>
            <div className="checkout-bar">
              <span>运费：{money(0, data.currency)}</span>
              <strong>合计 {money(data.total, data.currency)}</strong>
              <button disabled={busy || !selectedAddress || addresses.loading} onClick={submit}>
                {busy ? '提交中…' : '提交演示订单'}
              </button>
            </div>
          </>
        )}
        {error && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              setAttempt((n) => n + 1)
              setRequestKey(crypto.randomUUID())
            }}
          >
            重新加载价格
          </button>
        )}
      </section>
    </>
  )
}
export default function Checkout() {
  const auth = useAuth()
  return <ShopShell title="确认订单">{auth.user && <CheckoutContent />}</ShopShell>
}
