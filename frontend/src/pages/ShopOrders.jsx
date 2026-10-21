import { useState } from 'react'
import { Link,useSearchParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import OrderView from '../components/OrderView'
import { useAuth } from '../auth/useAuth'
import { statuses, useShop } from '../lib/shop'

function OrderList({admin}){
 const [params]=useSearchParams()
 const [status,setStatus]=useState(''),[page,setPage]=useState(1),[query,setQuery]=useState(admin ? params.get('q') || '':''),[search,setSearch]=useState(admin ? params.get('q') || '':'')
 const orders=useShop(`${admin ? '/api/admin':'/api/shop'}/orders?${new URLSearchParams({status,page:String(page),...(admin ? {q:search}:{})})}`)
 return <><p className="demo-note">以下为数据库保存的演示订单，模拟支付不产生真实扣款。</p><div className="shop-toolbar"><div className="tabs">{Object.entries({'':'全部订单',...statuses}).map(([value,label])=><button key={value} className={status===value ? 'selected':''} onClick={()=>{setStatus(value);setPage(1)}}>{label}</button>)}</div><button className="secondary" onClick={orders.retry}>刷新订单</button></div>{admin && <form className="admin-search" onSubmit={e=>{e.preventDefault();setSearch(query.trim());setPage(1)}}><input aria-label="搜索订单编号" maxLength={40} placeholder="搜索订单编号" value={query} onChange={e=>setQuery(e.target.value)}/><button>搜索</button></form>}{orders.loading || orders.error ? <CatalogStatus {...orders}/> : <><p>共 {orders.data.total} 笔订单</p>{orders.data.items.map(order=><OrderView key={order.id} order={order} admin={admin} onChange={orders.retry}/>)}{!orders.data.items.length && <section className="panel shop-empty"><h2>暂无订单</h2><Link className="button secondary" to="/products">去逛商品</Link></section>}<nav className="pagination" aria-label="订单分页"><button className="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page} / {orders.data.total_pages || 1}</span><button className="secondary" disabled={page>=orders.data.total_pages} onClick={()=>setPage(p=>p+1)}>下一页</button></nav></>}</>
}
export default function ShopOrders({admin=false}){const auth=useAuth();return <ShopShell title={admin ? '订单管理':'我的订单'} admin={admin}>{auth.user && (!admin || auth.isAdmin) && <OrderList admin={admin}/>}</ShopShell>}
