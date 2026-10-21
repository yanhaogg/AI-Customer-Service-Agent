import { useState } from 'react'
import { Link } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import AddressForm from '../components/AddressForm'
import CatalogStatus from '../components/CatalogStatus'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop } from '../lib/shop'

export default function Addresses() {
  const auth = useAuth(),
    addresses = useShop('/api/shop/addresses')
  const [editor, setEditor] = useState(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  async function remove(id) {
    setBusy(true)
    setError('')
    try {
      await shopRequest(auth.token, `/api/shop/addresses/${id}`, {
        method: 'DELETE',
      })
      addresses.retry()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <ShopShell title="收货地址">
      <div className="shop-toolbar">
        <p>保存联系人和配送地址，结算时可直接选择。</p>
        <button onClick={() => setEditor({})}>＋ 新增地址</button>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {editor && (
        <section className="panel shop-panel">
          <h2>{editor.id ? '编辑收货地址' : '新增收货地址'}</h2>
          <AddressForm
            key={editor.id || 'new'}
            address={editor.id ? editor : null}
            onCancel={() => setEditor(null)}
            onSaved={() => {
              setEditor(null)
              addresses.retry()
            }}
          />
        </section>
      )}
      {addresses.loading || addresses.error ? (
        <CatalogStatus {...addresses} />
      ) : (
        <div className="address-grid">
          {addresses.data?.items.map((a) => (
            <section className="panel address-card" key={a.id}>
              <strong>
                {a.recipient} · {a.phone}
              </strong>
              {a.is_default && <span className="pill">默认地址</span>}
              <p>{a.region}</p>
              <p>
                {a.detail} {a.postal_code}
              </p>
              <div className="management-actions">
                <button className="secondary" disabled={busy} onClick={() => setEditor(a)}>
                  编辑
                </button>
                <button className="danger-button" disabled={busy} onClick={() => remove(a.id)}>
                  删除
                </button>
              </div>
            </section>
          ))}
          {addresses.data?.items.length === 0 && <p>还没有收货地址，点击上方新增。</p>}
        </div>
      )}
      <Link to="/cart">返回购物车 →</Link>
    </ShopShell>
  )
}
