import { useEffect,useRef,useState } from 'react'
import { Link,useNavigate,useSearchParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import ChatText from '../components/ChatText'
import UnreadBadge from '../components/UnreadBadge'
import AgentCollaboration from '../components/AgentCollaboration'
import StaffAssistant from '../components/StaffAssistant'
import { useUnread,useConversationRead } from '../lib/chat'
import { useAuth } from '../auth/useAuth'
import { shopRequest,useShop } from '../lib/shop'

function StaffThread({id,onChange}){
 const {token}=useAuth(),thread=useShop(`/api/admin/support-sessions/${id}`,{keepPrevious:true})
 const [draft,setDraft]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[older,setOlder]=useState([]),[more,setMore]=useState(null)
 useConversationRead(`/api/admin/support-sessions/${id}`,thread.data)
 const key=useRef(crypto.randomUUID()),messageLog=useRef(null),replyBox=useRef(null),retry=thread.retry
 const latestMessageId=thread.data?.items.at(-1)?.id
 useEffect(()=>{messageLog.current?.scrollTo({top:messageLog.current.scrollHeight,behavior:'smooth'})},[latestMessageId])
 useEffect(()=>{const timer=setInterval(retry,4000);return ()=>clearInterval(timer)},[retry])
 function applySuggestion(text){setDraft(text);key.current=crypto.randomUUID();replyBox.current?.focus();replyBox.current?.scrollIntoView({behavior:'smooth',block:'center'})}
 async function send(e){
  e.preventDefault();setBusy(true);setError('')
  try{await shopRequest(token,`/api/admin/support-sessions/${id}/messages`,{method:'POST',body:JSON.stringify({content:draft,request_key:key.current})});setDraft('');key.current=crypto.randomUUID();thread.retry();onChange()}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function close(){
  setBusy(true);setError('')
  try{await shopRequest(token,`/api/admin/support-sessions/${id}/close`,{method:'POST'});thread.retry();onChange()}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function earlier(){
  const first=older[0]?.id || thread.data?.items[0]?.id
  if(!first)return
  try{const result=await shopRequest(token,`/api/admin/support-sessions/${id}?before_id=${first}`);setOlder(entries=>[...result.items,...entries]);setMore(result.has_more)}catch(err){setError(err.message)}
 }
 if(thread.error || (!thread.data && thread.loading))return <CatalogStatus {...thread}/>
 if(!thread.data)return null
 const session=thread.data.session,messages=[...older,...thread.data.items].filter((m,index,all)=>all.findIndex(x=>x.id===m.id)===index)
 return <section className="panel chat-panel"><div className="chat-header"><div><strong>{session.title}</strong><p>{session.context_name || '日常商品咨询'} · {session.human_status==='none' ? 'AI 咨询':session.human_status==='waiting' ? '待接待':session.human_status==='active' ? '人工接待中':'已结束'}</p>{session.order_id && <Link to={`/admin/orders?q=${encodeURIComponent(session.context_name || '')}`}>查看关联订单与售后 →</Link>}</div><button className="secondary" disabled={busy || !['waiting','active'].includes(session.human_status)} onClick={close}>结束接待</button></div><section className="linked-support-tasks"><Link to="/admin/tasks">客服待办 →</Link>{thread.data.support_tasks?.map(task=><Link key={task.id} to={`/admin/tasks?task=${task.id}`}>{task.title} · {task.status==='in_progress' ? '处理中':'待认领'}</Link>)}</section><StaffAssistant id={id} version={thread.data.assist_version} onUse={applySuggestion} disabled={busy || session.human_status==='closed'} hasDraft={!!draft.trim()}/><div ref={messageLog} className="chat-messages" role="log">{(more ?? thread.data.has_more) && <button className="secondary" onClick={earlier}>更早消息</button>}{messages.map(m=><div className={`message ${m.is_mine ? 'outgoing':'incoming'} ${m.role==='human_agent' ? 'human-message':''}`} key={m.id}><span>{m.is_mine ? '我':m.role==='user' ? '用户':m.role==='human_agent' ? '客服':'AI'}</span><div className="saved-message"><ChatText text={m.content || '正在处理…'}/><AgentCollaboration metadata={m.agent_metadata}/><small>{new Date(m.created_at).toLocaleString('zh-CN')}</small></div></div>)}</div><form className="chat-compose" onSubmit={send}>{error && <p className="form-error" role="alert">{error}</p>}<label htmlFor="staff-reply">人工客服回复</label><textarea ref={replyBox} id="staff-reply" required maxLength={10000} disabled={busy || session.human_status==='closed'} value={draft} onChange={e=>{setDraft(e.target.value);key.current=crypto.randomUUID()}} rows={3}/><div><small>发送回复将接管此会话并暂停 AI 自动回复。退款请在关联订单中按流程审核。</small><button disabled={busy || !draft.trim() || session.human_status==='closed'}>发送并接待</button></div></form></section>
}

function Inbox(){
 const [params]=useSearchParams(),navigate=useNavigate()
 const unread=useUnread(true)
 const [status,setStatus]=useState('all'),[page,setPage]=useState(1),[unreadOnly,setUnreadOnly]=useState(false)
 const data=useShop(`/api/admin/support-sessions?${new URLSearchParams({status,page:String(page),unread_only:String(unreadOnly)})}`,{keepPrevious:true})
 const selected=params.get('session') || data.data?.items[0]?.id
 const refresh=data.retry,firstSessionId=data.data?.items[0]?.id
 useEffect(()=>{if(!params.get('session') && firstSessionId)navigate(`/admin/support?session=${firstSessionId}`,{replace:true})},[params,firstSessionId,navigate])
 useEffect(()=>{const timer=setInterval(refresh,5000);window.addEventListener('chat-read',refresh);return ()=>{clearInterval(timer);window.removeEventListener('chat-read',refresh)}},[refresh])
 return <><p className="page-description">查看所有客户与 AI、人工客服的会话；发送回复即可转为人工接待。</p><label className="unread-filter"><input type="checkbox" checked={unreadOnly} onChange={e=>{setUnreadOnly(e.target.checked);setPage(1);navigate('/admin/support')}}/>只看未读</label><div className="tabs">{[['all','全部会话'],['none','AI 咨询'],['waiting','待接待'],['active','接待中'],['closed','已结束']].map(([value,label])=><button className={status===value ? 'selected':''} key={value} onClick={()=>{setStatus(value);setPage(1);navigate('/admin/support')}}>{label}</button>)}</div><div className="chat-layout saved-chat-layout"><aside className="panel conversation-sidebar">{(data.loading && !data.data) || data.error ? <CatalogStatus {...data}/> : <>{data.data.items.map(session=><button className={`staff-session ${String(selected)===String(session.id) ? 'selected':''}`} key={session.id} onClick={()=>navigate(`/admin/support?session=${session.id}`)}><strong>{session.title} <UnreadBadge count={unread.sessions[session.id] || 0}/></strong><small>{session.customer_name} · {new Date(session.updated_at).toLocaleString('zh-CN')}</small></button>)}{!data.data.items.length && <p>{unreadOnly ? '当前筛选下没有未读会话。':'当前没有会话。'}</p>}<nav className="pagination"><button className="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page} / {data.data.total_pages || 1}</span><button className="secondary" disabled={page>=data.data.total_pages} onClick={()=>setPage(p=>p+1)}>下一页</button></nav></>}</aside>{selected ? <StaffThread key={selected} id={selected} onChange={data.retry}/>:<section className="panel shop-empty">请选择一个人工会话。</section>}</div></>
}
export default function HumanSupport(){const auth=useAuth();return <ShopShell title="客服工作台" admin>{auth.isAdmin && <Inbox/>}</ShopShell>}
