import { Link, useLocation } from 'react-router-dom'
import Navbar from './Navbar'
import CatalogStatus from './CatalogStatus'
import { useAuth } from '../auth/useAuth'

export default function ShopShell({children,title,admin=false}){
 const auth=useAuth(),location=useLocation()
 const allowed=auth.user && (!admin || auth.isAdmin)
 return <><Navbar/><main className="container page shop-page"><h1>{title}</h1>{auth.loading ? <CatalogStatus loading/> : allowed ? children : <section className="panel shop-empty"><h2>{auth.user ? '仅超级管理员可以访问' : '请先登录'}</h2><p>{auth.error || '登录后可管理购物车、收货地址和订单。'}</p><Link className="button" to={`/login?redirect=${encodeURIComponent(location.pathname+location.search)}`}>前往登录</Link></section>}</main></>
}
