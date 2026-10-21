import { useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { apiUrl } from '../lib/catalog'
import { Link, useNavigate } from 'react-router-dom'
export default function AuthPage({ register = false }) {
 const navigate = useNavigate()
 const auth = useAuth()
 const requested = new URLSearchParams(window.location.search).get('redirect')
 const redirect = requested?.startsWith('/') && !requested.startsWith('//') && !requested.includes(String.fromCharCode(92)) ? requested : '/home'
 const [username,setUsername] = useState(''), [password,setPassword] = useState(''), [loading,setLoading] = useState(false), [error,setError] = useState('')
 async function submit(event) {
  event.preventDefault(); setLoading(true); setError('')
  try {
   const res = await fetch(apiUrl(`/auth/${register ? 'register' : 'login'}`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})})
   const data = await res.json()
   if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查输入信息后重试。')
   if (register) navigate(`/login?registered=1&redirect=${encodeURIComponent(redirect)}`)
   else { if (!data.access_token) throw new Error('登录失败，请稍后重试。'); auth.login(data.access_token); localStorage.setItem('username',username); navigate(redirect) }
  } catch(err) { setError(err.message === 'Failed to fetch' ? '暂时无法连接服务，请确认后端已启动。' : err.message) }
  finally { setLoading(false) }
 }
 return <div className="auth-page"><header className="container auth-header"><Link className="brand" to="/login"><span className="brand-mark">S·</span><span>ServAI<small>购物服务中心</small></span></Link><span>让每一次购物，都安心一点。</span></header><main className="auth-main container"><section className="auth-intro"><span className="eyebrow">A BETTER SHOPPING EXPERIENCE</span><h1>购物的快乐，<br/>我们一起守护。</h1><p>从订单查询到售后咨询，<br/>你的专属智能助手，随时在这里。</p><div className="auth-art" aria-hidden="true"><div className="art-bag"><div className="bag-handle"/><span>S·</span><small>MADE FOR YOUR EVERYDAY</small></div><span className="auth-art-label">✧ 贴心服务，轻松生活</span></div></section><section className="auth-card"><span className="eyebrow">{register ? 'JOIN US' : 'WELCOME BACK'}</span><h2>{register ? '开启你的专属服务' : '欢迎回来'}</h2><p>{register ? '创建账号，让购物服务触手可及。' : '登录账号，继续你的安心购物之旅。'}</p>{!register && new URLSearchParams(window.location.search).has('registered') && <p className="success-note" role="status">注册成功，请登录。</p>}<form onSubmit={submit}><label htmlFor="username">用户名</label><input id="username" autoComplete="username" placeholder="请输入用户名" required value={username} onChange={e => setUsername(e.target.value)}/><label htmlFor="password">密码</label><input id="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} placeholder="请输入密码" minLength={register ? 8 : 1} required value={password} onChange={e => setPassword(e.target.value)}/>{error && <p role="alert" className="form-error">{error}</p>}<button disabled={loading} className="auth-submit">{loading ? '请稍候…' : register ? '注册账号 →' : '登录 →'}</button></form><div className="auth-switch">{register ? '已有账号？' : '还没有账号？'} <Link to={`${register ? '/login' : '/register'}?redirect=${encodeURIComponent(redirect)}`}>{register ? '前往登录' : '立即注册'}</Link></div><div className="auth-assurance">订单服务 · 售后咨询 · 智能陪伴</div></section></main><footer className="container footer"><span>ServAI · 用心服务每一次购物</span><span>你的智能购物服务伙伴</span></footer></div>
}
