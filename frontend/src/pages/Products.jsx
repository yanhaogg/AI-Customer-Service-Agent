import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Navbar from '../components/Navbar'
import ProductCard from '../components/ProductCard'
import CatalogStatus from '../components/CatalogStatus'
import { useCatalog } from '../lib/catalog'
export default function Products() {
 const [params,setParams] = useSearchParams()
 const category = params.get('category') || '', query = params.get('q') || '', sort = params.get('sort') || 'recommended'
 const page = Math.max(1, Number.parseInt(params.get('page') || '1', 10) || 1)
 const [draft,setDraft] = useState({ query, text: query })
 const draftQuery = draft.query === query ? draft.text : query
 const setDraftQuery = text => setDraft({ query, text })
 const categories = useCatalog('/categories')
 const search = new URLSearchParams({ q: query, sort, page: String(page), page_size: '24' })
 if (category) search.set('category', category)
 const catalog = useCatalog(`/products?${search}`)
 const data = catalog.data
 function change(values) {
  const next = new URLSearchParams(params)
  Object.entries(values).forEach(([key,value]) => value ? next.set(key, String(value)) : next.delete(key))
  if (!Object.hasOwn(values,'page')) next.delete('page')
  setParams(next)
 }
 return <><Navbar/><main className="container page"><div className="catalog-heading"><div><span className="eyebrow">DESIGNED FOR EVERYDAY</span><h1>找到你的日常好物</h1><p className="page-description">从通勤到居家，从办公到放松。让科技自然融入生活。</p></div><form className="catalog-search" onSubmit={e=>{e.preventDefault();const text=draftQuery.trim();setDraft({query:text,text});change({q:text})}}><label className="sr-only" htmlFor="product-search">搜索商品</label><input id="product-search" type="search" maxLength={150} value={draftQuery} onChange={e=>setDraftQuery(e.target.value)} placeholder="搜索商品、品牌或型号…"/><button type="submit" aria-label="搜索商品">搜索</button></form></div><div className="catalog-filters"><div className="category-tabs" aria-label="商品分类"><button className={!category ? 'active' : ''} aria-pressed={!category} onClick={()=>change({category:''})}>全部商品</button>{categories.data?.items.map(item=><button key={item.code} className={category === item.code ? 'active' : ''} aria-pressed={category === item.code} onClick={()=>change({category:item.code})}>{item.name}<small>{item.count}</small></button>)}</div><label className="sort-control">排序 <select value={sort} onChange={e=>change({sort:e.target.value})}><option value="recommended">推荐顺序</option><option value="price_asc">历史价格从低到高</option><option value="price_desc">历史价格从高到低</option></select></label></div>{categories.error && <p className="form-error">分类暂时无法加载 <button className="secondary" onClick={categories.retry}>重试</button></p>}<p className="catalog-count"><span>{data ? `共 ${data.total} 件商品${query ? ` · 搜索「${query}」` : ''}` : '正在查找商品…'}</span><span>历史资料 · 原始币种参考价 · 暂未开放下单</span></p>{catalog.loading || catalog.error ? <CatalogStatus {...catalog}/> : data.items.length ? <><div className="catalog-grid">{data.items.map(product=><ProductCard key={product.id} product={product}/>)}</div><nav className="pagination" aria-label="商品分页"><button className="secondary" disabled={page <= 1} onClick={()=>change({page:page-1})}>← 上一页</button><span>第 {page} / {data.total_pages} 页</span><button className="secondary" disabled={page >= data.total_pages} onClick={()=>change({page:page+1})}>下一页 →</button></nav></> : <div className="empty-catalog"><h2>暂时没有找到相关商品</h2><p>换个关键词，或试试其他分类。</p><button className="secondary" onClick={()=>{setDraft({query:'',text:''});setParams({})}}>查看全部商品</button></div>}</main></>
}
