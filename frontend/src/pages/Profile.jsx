import ShopShell from '../components/ShopShell'
import { useAuth } from '../auth/useAuth'
import { Link,useNavigate } from 'react-router-dom'

export default function Profile(){
 const navigate=useNavigate(),auth=useAuth()
 function logout(){auth.logout();navigate('/login')}
 return <ShopShell title="个人中心">{auth.user && <>
  <p className="page-description">属于你的购物服务空间。</p>
  <section className="panel profile-panel">
   <div className="profile-summary"><span className="avatar">{auth.user.username.slice(0,1).toUpperCase()}</span><div><h2>{auth.user.username}</h2><p>欢迎使用 ServAI 购物服务</p></div></div>
   <div className="profile-links">
    {auth.isAdmin && <><Link to="/admin/homepage"><span>首页商品管理</span>配置首页 →</Link><Link to="/admin/products"><span>商品管理</span>维护商品 →</Link><Link to="/admin/orders"><span>订单管理</span>处理发货 →</Link><Link to="/admin/support"><span>客服工作台</span>接待会话 →</Link><Link to="/admin/tasks"><span>客服待办</span>跟进订单异常 →</Link></>}
    <Link to="/history"><span>最近浏览</span>查看浏览记录 →</Link><Link to="/addresses"><span>收货地址</span>管理地址 →</Link><Link to="/cart"><span>购物车</span>查看购物车 →</Link><Link to="/orders"><span>▤ 我的订单</span>查看订单 →</Link><Link to="/chat"><span>✧ 客服与聊天记录</span>继续咨询 →</Link>
   </div>
   <button className="secondary" onClick={logout}>退出登录</button>
  </section>
 </>}</ShopShell>
}
