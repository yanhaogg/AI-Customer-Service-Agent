import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import CatalogImage from '../components/CatalogImage'
import CatalogStatus from '../components/CatalogStatus'
import { useAuth } from '../auth/useAuth'
import { apiUrl, displayName, useCatalog } from '../lib/catalog'

function HomepageEditor() {
 const auth=useAuth()
 const [config,setConfig]=useState(null),[error,setError]=useState(''),[saved,setSaved]=useState(''),[saving,setSaving]=useState(false)
 const [reload,setReload]=useState(0),[query,setQuery]=useState(''),[search,setSearch]=useState(''),[category,setCategory]=useState('')
 const [page,setPage]=useState(1),[target,setTarget]=useState('hero')
 const categories=useCatalog('/categories')
 const catalog=useCatalog(`/products?${new URLSearchParams({q:search,category,page:String(page),page_size:'12'})}`)
 useEffect(()=>{
  const controller=new AbortController()
  fetch(apiUrl('/api/admin/homepage'),{headers:{Authorization:`Bearer ${auth.token}`},signal:controller.signal})
   .then(async response=>{const body=await response.json();if (!response.ok) throw new Error(body.detail || '首页配置读取失败');return body})
   .then(data=>{if (!controller.signal.aborted){setConfig(data);setError('');setSaved('')}})
   .catch(err=>{if (!controller.signal.aborted)setError(err.message)})
  return ()=>controller.abort()
 },[auth.token,reload])
 function selectProduct(product) {
  const all=[config.preview.hero,...config.preview.spotlights,...config.preview.featured].filter(Boolean)
  if (all.some(item=>item.id===product.id)) {setError('这款商品已经在首页中，请先移除或换一款商品。');return}
  if (target!=='hero' && config.preview[target].length >= (target==='spotlights' ? 2 : 8)) {setError('该区域已满，请先移除一个商品。');return}
  setConfig(previous=>({...previous,preview:{...previous.preview,[target]:target==='hero' ? product : [...previous.preview[target],product]}}))
  setError('');setSaved('')
 }
 function remove(section,id) {setConfig(previous=>({...previous,preview:{...previous.preview,[section]:previous.preview[section].filter(item=>item.id!==id)}}));setSaved('')}
 function move(section,index,direction) {
  setConfig(previous=>{const items=[...previous.preview[section]];const next=index+direction;if(next<0||next>=items.length)return previous;[items[index],items[next]]=[items[next],items[index]];return {...previous,preview:{...previous.preview,[section]:items}}});setSaved('')
 }
 async function save() {
  if (!config.preview.hero) return
  setSaving(true);setError('');setSaved('')
  try {
   const response=await fetch(apiUrl('/api/admin/homepage'),{method:'PUT',headers:{Authorization:`Bearer ${auth.token}`,'Content-Type':'application/json'},body:JSON.stringify({hero_product_id:config.preview.hero.id,spotlight_ids:config.preview.spotlights.map(item=>item.id),featured_ids:config.preview.featured.map(item=>item.id),revision:config.revision})})
   const body=await response.json()
   if (response.status===401 || response.status===403) auth.refresh()
   if (!response.ok) throw new Error(typeof body.detail==='string' ? body.detail : '配置有误，请检查商品是否重复或区域数量是否超限。')
   setConfig(body);setSaved('已保存，公开首页已更新。')
  } catch(err) {setError(err.message)} finally {setSaving(false)}
 }
 const sections=[['hero','首屏主推',1],['spotlights','双栏推荐',2],['featured','日常好物',8]]
 return <main className="container page admin-page"><span className="eyebrow">HOMEPAGE MANAGEMENT</span><div className="admin-title"><div><h1>首页商品管理</h1><p className="page-description">选择展示商品、调整顺序，保存后同步到公开首页。</p></div><Link className="button secondary" to="/home">查看公开首页 ↗</Link></div>{error && <p role="alert" className="form-error">{error}</p>}{saved && <p className="success-note" role="status">{saved}</p>}{!config ? error ? <button onClick={()=>setReload(value=>value+1)}>重新加载</button> : <CatalogStatus loading/> : <><section className="admin-selection-grid">{sections.map(([section,label,max])=>{const items=section==='hero' ? [config.preview.hero].filter(Boolean) : config.preview[section];return <div key={section} className={`panel admin-selection ${target===section ? 'selected' : ''}`}><button className="admin-region" disabled={saving} onClick={()=>setTarget(section)}><strong>{label}</strong><small>{items.length} / {max} · {target===section ? '正在选品' : '点击选品'}</small></button>{items.map((item,index)=><div className="selected-product" key={item.id}><CatalogImage product={item}/><div><strong title={item.name}>{displayName(item)}</strong><small>商品 #{item.id}</small>{section!=='hero' && <div className="selection-actions"><button disabled={saving || index===0} onClick={()=>move(section,index,-1)} aria-label={`前移 ${item.name}`}>↑</button><button disabled={saving || index===items.length-1} onClick={()=>move(section,index,1)} aria-label={`后移 ${item.name}`}>↓</button><button disabled={saving} onClick={()=>remove(section,item.id)}>移除</button></div>}</div></div>)}{section==='hero' && <p className="admin-hint">在下方选择另一款商品即可替换首屏主推。</p>}</div>})}</section><div className="admin-save-bar"><span>当前修改尚需点击保存。首屏 1 件，双栏最多 2 件，日常好物最多 8 件。</span><div><button className="secondary" disabled={saving} onClick={()=>setReload(value=>value+1)}>重新加载</button><button disabled={saving || !config.preview.hero} onClick={save}>{saving ? '保存中…' : '保存首页配置'}</button></div></div><section className="panel admin-product-picker"><h2>选择商品</h2><p>当前目标：{sections.find(([section])=>section===target)[1]}</p><form className="admin-search" onSubmit={event=>{event.preventDefault();setSearch(query.trim());setPage(1)}}><label className="sr-only" htmlFor="admin-search">查找商品</label><input id="admin-search" value={query} maxLength={150} onChange={event=>setQuery(event.target.value)} placeholder="搜索名称、品牌或型号"/><select aria-label="选品分类" value={category} onChange={event=>{setCategory(event.target.value);setPage(1)}}><option value="">全部分类</option>{categories.data?.items.map(item=><option key={item.code} value={item.code}>{item.name}</option>)}</select><button>搜索</button></form>{catalog.loading || catalog.error ? <CatalogStatus {...catalog}/> : <><p className="catalog-count">共 {catalog.data.total} 件商品</p><div className="admin-picker-grid">{catalog.data.items.map(product=><div key={product.id} className="admin-picker-card"><CatalogImage product={product}/><strong title={product.name}>{displayName(product)}</strong><small>{product.category} · #{product.id}</small><button disabled={saving} className="secondary" onClick={()=>selectProduct(product)}>{target==='hero' ? '设为首屏主推' : '加入当前区域'}</button></div>)}</div><nav className="pagination" aria-label="选品分页"><button className="secondary" disabled={page===1} onClick={()=>setPage(value=>value-1)}>上一页</button><span>{page} / {catalog.data.total_pages || 1}</span><button className="secondary" disabled={page>=catalog.data.total_pages} onClick={()=>setPage(value=>value+1)}>下一页</button></nav></>}</section></>}</main>
}
export default function AdminHomepage() {
 const auth=useAuth()
 return <><Navbar/>{auth.loading ? <div className="container page"><CatalogStatus loading/></div> : auth.isAdmin ? <HomepageEditor/> : <main className="container page"><div className="empty-catalog"><h1>{auth.token ? '无权访问此页面' : '请先登录'}</h1><p>{auth.error || '首页商品管理仅对超级管理员开放。'}</p>{!auth.user && <Link className="button" to="/login">前往登录</Link>}<Link className="button secondary" to="/home">返回首页</Link></div></main>}</>
}
