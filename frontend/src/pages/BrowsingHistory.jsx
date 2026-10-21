import { useState } from 'react'
import { Link } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogImage from '../components/CatalogImage'
import CatalogStatus from '../components/CatalogStatus'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop, money } from '../lib/shop'

export default function BrowsingHistory() {
  const auth = useAuth()
  const [page, setPage] = useState(1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [confirm, setConfirm] = useState(false)
  const history = useShop(`/api/activity/browsing?page=${page}`)
  async function remove(id) {
    setBusy(true)
    setError('')
    try {
      await shopRequest(auth.token, `/api/activity/browsing${id ? `/${id}` : ''}`, {
        method: 'DELETE',
      })
      setConfirm(false)
      setPage(1)
      history.retry()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <ShopShell title="最近浏览">
      <div className="shop-toolbar">
        <p>记录你打开过的商品，同款商品合并，最近查看的排在前面。</p>
        <button
          className="secondary"
          disabled={busy || !history.data?.total}
          onClick={() => setConfirm(true)}
        >
          清空浏览记录
        </button>
      </div>
      {confirm && (
        <section
          className="panel history-confirm"
          role="alertdialog"
          aria-labelledby="clear-history-title"
        >
          <h2 id="clear-history-title">清空全部浏览记录？</h2>
          <p>只清除当前账号的浏览记录，不影响商品、订单或聊天。</p>
          <div className="management-actions">
            <button className="danger-button" disabled={busy} onClick={() => remove(null)}>
              确认清空
            </button>
            <button className="secondary" disabled={busy} onClick={() => setConfirm(false)}>
              取消
            </button>
          </div>
        </section>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {history.loading || history.error ? (
        <CatalogStatus {...history} />
      ) : (
        <>
          <p>共 {history.data?.total || 0} 款商品</p>
          <div className="browsing-grid">
            {history.data?.items.map((item) => (
              <article className="panel browsing-card" key={item.id}>
                <CatalogImage product={item.product || item} />
                <div>
                  {item.available ? (
                    <Link to={`/products/${item.product_id}`}>
                      <h2>{item.product.name}</h2>
                    </Link>
                  ) : (
                    <>
                      <h2>{item.name}</h2>
                      <span className="pill">商品已删除或不可展示</span>
                    </>
                  )}
                  <p>
                    {new Date(item.last_viewed_at).toLocaleString('zh-CN')} · 浏览 {item.view_count}{' '}
                    次
                  </p>
                  {item.product?.offer?.is_active && (
                    <strong>{money(item.product.offer.amount, item.product.offer.currency)}</strong>
                  )}
                  <div className="management-actions">
                    {item.available && (
                      <Link className="button secondary" to={`/products/${item.product_id}`}>
                        再次查看
                      </Link>
                    )}
                    <button className="secondary" disabled={busy} onClick={() => remove(item.id)}>
                      移除记录
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          {history.data?.total === 0 && (
            <section className="panel shop-empty">
              <h2>还没有浏览记录</h2>
              <Link className="button" to="/products">
                去逛商品
              </Link>
            </section>
          )}
          <nav className="pagination" aria-label="浏览记录分页">
            <button
              className="secondary"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </button>
            <span>
              {page} / {history.data?.total_pages || 1}
            </span>
            <button
              className="secondary"
              disabled={!history.data || page >= history.data.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </nav>
        </>
      )}
    </ShopShell>
  )
}
