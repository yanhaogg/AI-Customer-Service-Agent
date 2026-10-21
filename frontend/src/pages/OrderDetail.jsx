import { Link, useParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import OrderView from '../components/OrderView'
import { useShop } from '../lib/shop'

export default function OrderDetail(){
 const {id}=useParams(),order=useShop(`/api/shop/orders/${encodeURIComponent(id)}`)
 return <ShopShell title="订单详情"><p className="demo-note">本订单仅用于演示。点击模拟支付不会产生真实扣款。</p><div className="shop-toolbar"><Link to="/orders">← 我的订单</Link><button className="secondary" onClick={order.retry}>刷新状态</button></div>{order.loading || order.error ? <CatalogStatus {...order}/> : order.data && <OrderView order={order.data} onChange={order.retry}/>}</ShopShell>
}
