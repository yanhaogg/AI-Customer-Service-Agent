import { NavLink, Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useUnread } from '../lib/chat'
import UnreadBadge from './UnreadBadge'
import { useTaskSummary } from '../lib/supportTasks'

export default function Navbar() {
  const {isAdmin} = useAuth()
  const tasks=useTaskSummary(isAdmin)
  const customerUnread=useUnread(),staffUnread=useUnread(true,isAdmin)
  return <>
    <div className="topbar"><div className="container"><span>欢迎来到 ServAI · 为日常，造好物。</span><Link to="/chat">帮助与客服 ↗</Link></div></div>
    <header className="navbar container">
      <Link className="brand" to="/home"><span className="brand-mark">S<span>·</span></span><span>ServAI<small>日常科技好物</small></span></Link>
      <nav className="primary-navigation" aria-label="主导航">{[['/home','首页'],['/products','全部商品'],['/cart','购物车'],['/orders','我的订单'],['/chat','智能客服'],['/profile','个人中心']].map(([path,label]) => <NavLink key={path} to={path}>{label}{path==='/chat' && <UnreadBadge count={customerUnread.total}/>}</NavLink>)}</nav>
      <Link className="nav-help" to="/chat"><span className="online-dot"/> 服务随时在线</Link>
      {isAdmin && <nav className="admin-navigation" aria-label="管理导航"><span>管理后台</span><NavLink className="admin-nav-link" to="/admin/homepage">首页管理</NavLink><NavLink className="admin-nav-link" to="/admin/products">商品管理</NavLink><NavLink className="admin-nav-link" to="/admin/orders">订单管理</NavLink><NavLink className="admin-nav-link" to="/admin/support">客服工作台 <UnreadBadge count={staffUnread.total}/></NavLink><NavLink className="admin-nav-link" to="/admin/tasks">客服待办{tasks.data?.active>0 && <span className="unread-badge" aria-label={`${tasks.data.active} 项未完成待办`}>{tasks.data.active>99 ? '99+':tasks.data.active}</span>}</NavLink></nav>}
    </header>
  </>
}

