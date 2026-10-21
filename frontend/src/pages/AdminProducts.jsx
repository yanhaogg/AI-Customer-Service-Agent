import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import SaleOfferEditor from '../components/SaleOfferEditor'
import CatalogImage from '../components/CatalogImage'
import CatalogStatus from '../components/CatalogStatus'
import { useAuth } from '../auth/useAuth'
import { apiUrl, formatPrice } from '../lib/catalog'

const emptyForm = {
  category_id: '',
  name_original: '',
  name_zh: '',
  brand: '',
  model: '',
  description_original: '',
  introduction_zh: '',
  specs: {},
  image_asset_id: null,
  price_amount: '',
  price_currency: 'USD',
  updated_at: null,
}

function ProductManager() {
  const auth = useAuth()
  const [offerProduct, setOfferProduct] = useState(null)
  const [categories, setCategories] = useState([]),
    [list, setList] = useState(null),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  const [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [category, setCategory] = useState(''),
    [page, setPage] = useState(1),
    [reload, setReload] = useState(0)
  const [editor, setEditor] = useState(null),
    [params, setParams] = useState(''),
    [preview, setPreview] = useState(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [deleting, setDeleting] = useState(null)

  async function request(path, options = {}) {
    const response = await fetch(apiUrl(`/api/admin${path}`), {
      ...options,
      headers: {
        Authorization: `Bearer ${auth.token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })
    const body = response.status === 204 ? null : await response.json()
    if (response.status === 401 || response.status === 403) auth.refresh()
    if (!response.ok)
      throw new Error(
        typeof body?.detail === 'string'
          ? body.detail
          : '提交信息有误，请检查必填字段、价格和参数格式。',
      )
    return body
  }

  useEffect(() => {
    const controller = new AbortController()
    fetch(apiUrl('/api/admin/product-categories'), {
      headers: { Authorization: `Bearer ${auth.token}` },
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error('无法读取商品分类')
        return r.json()
      })
      .then((data) => setCategories(data.items))
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [auth.token])

  useEffect(() => {
    const controller = new AbortController()
    const url = new URLSearchParams({
      q: search,
      page: String(page),
      page_size: '12',
    })
    if (category) url.set('category_id', category)
    fetch(apiUrl(`/api/admin/products?${url}`), {
      headers: { Authorization: `Bearer ${auth.token}` },
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error('无法读取商品列表')
        return r.json()
      })
      .then((data) => {
        if (!controller.signal.aborted) setList(data)
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [auth.token, search, category, page, reload])

  function change(field, value) {
    setEditor((previous) => ({ ...previous, [field]: value }))
  }
  function startNew() {
    setEditor({ ...emptyForm, category_id: String(categories[0]?.id || '') })
    setParams('')
    setPreview(null)
    setError('')
    setNotice('')
  }
  async function edit(id) {
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const data = await request(`/products/${id}`)
      setEditor({
        ...emptyForm,
        ...data,
        brand: data.brand || '',
        model: data.model || '',
        category_id: String(data.category_id),
        price_amount: data.price?.amount ?? '',
        price_currency: data.price?.currency || 'USD',
      })
      setParams(
        Object.entries(data.specs)
          .map(
            ([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`,
          )
          .join('\n'),
      )
      setPreview(data.image)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  async function upload(file) {
    if (!file) return
    if (file.size > 5_000_000) {
      setError('图片大小不能超过 5MB')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result.split(',')[1])
        reader.onerror = () => reject(new Error('图片读取失败'))
        reader.readAsDataURL(file)
      })
      const result = await request('/product-images', {
        method: 'POST',
        body: JSON.stringify({ data }),
      })
      change('image_asset_id', result.asset_id)
      setPreview({ url: result.url })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function save(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    const specs = Object.create(null)
    for (const line of params.split('\n').filter((line) => line.trim())) {
      const separator = line.indexOf('=')
      const key = line.slice(0, separator).trim()
      if (separator < 1 || !key) {
        setError('参数请按“名称=值”填写，每行一个。')
        return
      }
      if (Object.hasOwn(specs, key)) {
        setError(`参数名称重复：${key}`)
        return
      }
      specs[key] = line.slice(separator + 1).trim()
    }
    setBusy(true)
    try {
      const body = Object.fromEntries(Object.keys(emptyForm).map((key) => [key, editor[key]]))
      body.category_id = Number(body.category_id)
      body.price_amount = body.price_amount === '' ? null : body.price_amount
      body.specs = specs
      await request(editor.id ? `/products/${editor.id}` : '/products', {
        method: editor.id ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      })
      setEditor(null)
      setReload((n) => n + 1)
      setNotice('商品已保存，公开商品页和首页将使用最新资料。')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function confirmDelete() {
    setBusy(true)
    setError('')
    try {
      await request(`/products/${deleting.id}`, { method: 'DELETE' })
      setDeleting(null)
      setEditor(null)
      setPage(1)
      setReload((n) => n + 1)
      setNotice('商品已删除，公开列表及首页选品已同步更新。')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="container page admin-page">
      <span className="eyebrow">PRODUCT MANAGEMENT</span>
      <div className="admin-title">
        <div>
          <h1>商品管理</h1>
          <p className="page-description">维护日常科技好物的资料、图片与参考价格。</p>
        </div>
        <div className="management-actions">
          <Link className="button secondary" to="/admin/homepage">
            首页选品 ↗
          </Link>
          <button disabled={busy || loading} onClick={startNew}>
            ＋ 新增商品
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="success-note">
          {notice}
        </p>
      )}
      {loading && <CatalogStatus loading />}
      {deleting && (
        <section className="panel delete-confirm" role="alertdialog" aria-labelledby="delete-title">
          <h2 id="delete-title">确认删除“{deleting.name}”？</h2>
          <p>
            商品会从公开列表和首页移除。如果它是首页主推，将自动选择另一款商品。原始资料与价格记录会保留。
          </p>
          <div className="management-actions">
            <button className="danger-button" disabled={busy} onClick={confirmDelete}>
              {busy ? '删除中…' : '确认删除'}
            </button>
            <button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>
              取消
            </button>
          </div>
        </section>
      )}
      {offerProduct && (
        <SaleOfferEditor
          productId={offerProduct}
          onClose={() => setOfferProduct(null)}
          onSaved={() => setReload((n) => n + 1)}
        />
      )}
      {editor && (
        <section className="panel product-editor">
          <h2>{editor.id ? `编辑商品 #${editor.id}` : '新增商品'}</h2>
          <form onSubmit={save}>
            <fieldset disabled={busy || loading}>
              <div className="product-form-grid">
                <label>
                  原文商品名称 *
                  <input
                    required
                    maxLength={500}
                    value={editor.name_original}
                    onChange={(e) => change('name_original', e.target.value)}
                  />
                </label>
                <label>
                  中文名称
                  <input
                    maxLength={500}
                    value={editor.name_zh}
                    onChange={(e) => change('name_zh', e.target.value)}
                  />
                </label>
                <label>
                  商品分类 *
                  <select
                    required
                    value={editor.category_id}
                    onChange={(e) => change('category_id', e.target.value)}
                  >
                    <option value="">选择分类</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  品牌
                  <input
                    maxLength={200}
                    value={editor.brand}
                    onChange={(e) => change('brand', e.target.value)}
                  />
                </label>
                <label>
                  型号
                  <input
                    maxLength={200}
                    value={editor.model}
                    onChange={(e) => change('model', e.target.value)}
                  />
                </label>
                <label>
                  参考价格
                  <input
                    type="number"
                    min="0"
                    max="9999999999.99"
                    step="0.01"
                    value={editor.price_amount}
                    onChange={(e) => change('price_amount', e.target.value)}
                    placeholder="可留空；已有价格需保留或更新"
                  />
                </label>
                <label>
                  币种
                  <select
                    value={editor.price_currency}
                    onChange={(e) => change('price_currency', e.target.value)}
                  >
                    {['USD', 'CNY', 'EUR', 'GBP', 'JPY', 'HKD'].map((currency) => (
                      <option key={currency}>{currency}</option>
                    ))}
                  </select>
                </label>
                <div className="admin-image-editor">
                  <CatalogImage
                    product={{
                      name: editor.name_zh || editor.name_original,
                      image: preview,
                    }}
                  />
                  <label>
                    上传商品图片
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={(e) => {
                        upload(e.target.files[0])
                        e.target.value = ''
                      }}
                    />
                  </label>
                  <small>JPEG、PNG 或 WebP，最多 5MB</small>
                  {preview && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        change('image_asset_id', null)
                        setPreview(null)
                      }}
                    >
                      移除图片
                    </button>
                  )}
                </div>
                <label className="full-width">
                  中文简要介绍 *
                  <textarea
                    required
                    maxLength={10000}
                    rows={3}
                    value={editor.introduction_zh}
                    onChange={(e) => change('introduction_zh', e.target.value)}
                  />
                </label>
                <label className="full-width">
                  原文详细介绍 *
                  <textarea
                    required
                    maxLength={30000}
                    rows={5}
                    value={editor.description_original}
                    onChange={(e) => change('description_original', e.target.value)}
                  />
                </label>
                <label className="full-width">
                  商品参数（每行一个：名称=值）
                  <textarea
                    rows={4}
                    value={params}
                    onChange={(e) => setParams(e.target.value)}
                    placeholder={'连接方式=蓝牙 5.3\n续航=24 小时'}
                  />
                  <small>修改已核实参数；导入时的原始参数和证据会保留。</small>
                </label>
              </div>
              <div className="management-actions">
                <button>{busy ? '保存中…' : '保存商品'}</button>
                <button type="button" className="secondary" onClick={() => setEditor(null)}>
                  取消编辑
                </button>
              </div>
            </fieldset>
          </form>
        </section>
      )}
      <section className="panel admin-product-picker">
        <form
          className="admin-search"
          onSubmit={(e) => {
            e.preventDefault()
            setSearch(query.trim())
            setPage(1)
          }}
        >
          <input
            aria-label="搜索商品"
            placeholder="搜索名称、品牌或型号"
            maxLength={150}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            aria-label="商品分类"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value)
              setPage(1)
            }}
          >
            <option value="">全部分类</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button>搜索</button>
        </form>
        {!list ? (
          <CatalogStatus loading />
        ) : (
          <>
            <p className="catalog-count">共 {list.total} 件商品</p>
            <div className="admin-picker-grid">
              {list.items.map((product) => (
                <article className="admin-picker-card" key={product.id}>
                  <CatalogImage product={product} />
                  <strong>{product.name}</strong>
                  <small>
                    {product.category} · #{product.id}
                  </small>
                  <span>{formatPrice(product.price)}</span>
                  <div className="management-actions">
                    <button
                      className="secondary"
                      disabled={busy || loading}
                      onClick={() => edit(product.id)}
                    >
                      编辑
                    </button>
                    <button
                      className="secondary"
                      disabled={busy || loading}
                      onClick={() => setOfferProduct(product.id)}
                    >
                      销售设置
                    </button>
                    <button
                      className="danger-button"
                      disabled={busy || loading}
                      onClick={() => {
                        setDeleting(product)
                        setError('')
                      }}
                    >
                      删除
                    </button>
                  </div>
                </article>
              ))}
            </div>
            {!list.items.length && <p>没有匹配的商品。</p>}
            <nav className="pagination" aria-label="商品管理分页">
              <button
                className="secondary"
                disabled={page === 1}
                onClick={() => setPage((n) => n - 1)}
              >
                上一页
              </button>
              <span>
                {page} / {list.total_pages || 1}
              </span>
              <button
                className="secondary"
                disabled={page >= list.total_pages}
                onClick={() => setPage((n) => n + 1)}
              >
                下一页
              </button>
            </nav>
          </>
        )}
      </section>
    </main>
  )
}

export default function AdminProducts() {
  const auth = useAuth()
  return (
    <>
      <Navbar />
      {auth.loading ? (
        <div className="container page">
          <CatalogStatus loading />
        </div>
      ) : auth.isAdmin ? (
        <ProductManager />
      ) : (
        <main className="container page">
          <div className="empty-catalog">
            <h1>{auth.token ? '无权访问此页面' : '请先登录'}</h1>
            <p>商品管理仅对超级管理员开放。</p>
            {!auth.user && (
              <Link className="button" to="/login">
                前往登录
              </Link>
            )}
            <Link className="button secondary" to="/home">
              返回首页
            </Link>
          </div>
        </main>
      )}
    </>
  )
}
