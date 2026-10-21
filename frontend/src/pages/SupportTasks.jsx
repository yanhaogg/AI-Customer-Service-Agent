import { useEffect,useState } from 'react'
import { Link,useNavigate,useSearchParams } from 'react-router-dom'
import ShopShell from '../components/ShopShell'
import CatalogStatus from '../components/CatalogStatus'
import ChatText from '../components/ChatText'
import ManualOrderAnalysis from '../components/ManualOrderAnalysis'
import { useAuth } from '../auth/useAuth'
import { shopRequest,useShop } from '../lib/shop'
import { taskKinds,taskStatuses,tasksChanged,useTaskSummary } from '../lib/supportTasks'

const eventLabels={created:'手动创建',detected:'发现异常',claimed:'认领',released:'释放',resolve:'完成',dismiss:'忽略',note:'跟进备注',
 auto_resolved:'系统关闭',analyzed:'生成分析',analysis_failed:'分析失败',facts_changed:'事实更新'}

function TaskDetail({id,onChange}){
 const {token,user}=useAuth(),navigate=useNavigate()
 const data=useShop(`/api/admin/support-tasks/${id}`,{keepPrevious:true})
 const [note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
 const refresh=data.retry
 useEffect(()=>{const timer=setInterval(refresh,8000);return ()=>clearInterval(timer)},[refresh])
 function changed(){data.retry();onChange();tasksChanged()}
 async function act(action){
  setBusy(true);setError('');setNotice('')
  try{await shopRequest(token,`/api/admin/support-tasks/${id}/actions`,{method:'POST',body:JSON.stringify({action,note})});setNote('');changed()}
  catch(err){setError(err.message);changed()}finally{setBusy(false)}
 }
 async function analyze(){
  setBusy(true);setError('');setNotice('')
  try{await shopRequest(token,`/api/admin/support-tasks/${id}/analyze`,{method:'POST'});changed()}
  catch(err){setError(err.message);changed()}finally{setBusy(false)}
 }
 async function contact(){
  setBusy(true);setError('')
  try{const result=await shopRequest(token,`/api/admin/support-tasks/${id}/conversation`,{method:'POST'});navigate(result.url)}
  catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function copy(text){
  try{await navigator.clipboard.writeText(text);setNotice('已复制建议，可进入订单会话粘贴、编辑后发送。')}
  catch{setError('暂时无法复制，请手动选中建议回复复制。')}
 }
 if(data.error || (!data.data && data.loading))return <CatalogStatus {...data}/>
 if(!data.data)return null
 const task=data.data,active=['pending','in_progress'].includes(task.status),other=task.assignee_id && task.assignee_id!==user.id
 const advice=task.advice || {}
 return <section className="panel task-detail">
  <div className="shop-toolbar"><div><span className="pill">{taskStatuses[task.status]}</span><h2>{task.title}</h2><p>订单 {task.order_number} · {task.assignee_name ? `负责人：${task.assignee_name}`:'尚未认领'}</p></div><Link to={task.order_url}>查看订单与售后 →</Link></div>
  {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="success-note" role="status">{notice}</p>}
  {task.facts_changed && active && <p className="assistant-stale">订单事实已变化，旧建议不再展示。请人工核实后重新分析，或完成、忽略此待办。</p>}<section><h3>分析时的订单快照</h3><p>订单状态：{({paid:'待发货',shipped:'待收货',completed:'已完成',refunded:'已退款',cancelled:'已取消'})[task.snapshot.order_status] || task.snapshot.order_status}</p><p>达到跟进阈值：{new Date(task.due_at).toLocaleString('zh-CN')}</p>{task.snapshot.refund && <p>关联退款申请：#{task.snapshot.refund.id} · {task.snapshot.refund.status}</p>}<p className="muted">{task.snapshot.logistics_note}</p></section>
  <section><h3>规则建议</h3><ol>{task.snapshot.recommended_actions.map(step=><li key={step}>{step}</li>)}</ol></section>
  <section className="task-analysis"><div className="shop-toolbar"><h3>订单异常跟进 Agent</h3><button className="secondary" disabled={busy || !active} onClick={analyze}>{busy ? '处理中…':task.analysis_status==='generating' ? '分析中，稍后重试':advice.analysis ? '重新分析':'生成跟进分析'}</button></div>
   {task.analysis_status==='pending' && <p className="muted">点击生成跟进分析后才会调用 Agent。</p>}
   {task.analysis_status==='generating' && <p role="status">正在根据订单事实分析，请稍候。</p>}
   {task.analysis_status==='failed' && <p className="form-error">上次分析未完成，可重试；待办与订单处理不受影响。</p>}
   {advice.analysis && <><ChatText text={advice.analysis}/><h3>建议步骤</h3><ol>{advice.next_steps.map((step,index)=><li key={index}>{step}</li>)}</ol><h3>客户回复草稿</h3><ChatText text={advice.suggested_reply}/><button className="secondary" onClick={()=>copy(advice.suggested_reply)}>复制建议回复</button></>}
  </section>
  <div className="management-actions"><button className="secondary" disabled={busy} onClick={contact}>进入订单会话</button>{active && <><button disabled={busy || !!other} onClick={()=>act('claim')}>{task.assignee_id===user.id ? '已由我认领':'认领待办'}</button>{task.assignee_id===user.id && <button className="secondary" disabled={busy} onClick={()=>act('release')}>释放认领</button>}</>}</div>
  <label htmlFor="task-note">跟进备注 / 处理说明</label><textarea id="task-note" maxLength={2000} rows={3} value={note} disabled={busy} onChange={e=>setNote(e.target.value)} placeholder="记录实际核实结果；完成或忽略时必须说明原因。"/>
  <div className="management-actions"><button className="secondary" disabled={busy || !note.trim()} onClick={()=>act('note')}>保存跟进备注</button>{active && <><button disabled={busy || !!other || !note.trim()} onClick={()=>act('resolve')}>完成待办</button><button className="secondary" disabled={busy || !!other || !note.trim()} onClick={()=>act('dismiss')}>忽略并记录原因</button></>}</div>
  <p className="muted">完成待办只记录跟进结果，发货、退款等操作仍需在订单页面执行。</p>{task.resolution_note && <p>关闭说明：{task.resolution_note}</p>}
  <h3>处理记录</h3><ol className="task-events">{task.events.map(event=><li key={event.id}><strong>{eventLabels[event.action] || event.action} · {event.actor}</strong><p>{event.note}</p><small>{new Date(event.created_at).toLocaleString('zh-CN')}</small></li>)}</ol>
 </section>
}

function Workspace(){
 const [params]=useSearchParams(),navigate=useNavigate(),summary=useTaskSummary()
 const [status,setStatus]=useState('active'),[kind,setKind]=useState(''),[mine,setMine]=useState(false),[page,setPage]=useState(1)
 const data=useShop(`/api/admin/support-tasks?${new URLSearchParams({status,kind,mine:String(mine),page:String(page),...(params.get('order') ? {order_id:params.get('order')}:{})})}`,{keepPrevious:true})
 const refresh=data.retry
 useEffect(()=>{const timer=setInterval(refresh,10000);window.addEventListener('support-tasks-changed',refresh);return ()=>{clearInterval(timer);window.removeEventListener('support-tasks-changed',refresh)}},[refresh])
 function selectTask(id){const next=new URLSearchParams(params);next.set('task',id);navigate(`/admin/tasks?${next}`)}
 function filter(setter,value){setter(value);setPage(1)}
 return <>
  <p className="page-description">管理员手动选择订单、分析情况并确认创建待办，再进行认领与跟进。</p>
  <ManualOrderAnalysis key={params.get('order') || 'manual'} initialOrderId={params.get('order') || ''} onCreated={selectTask}/>
  {params.get('order') && <p>正在查看指定订单的待办 · <Link to="/admin/tasks">查看全部订单</Link></p>}
  <div className="task-overview"><span>未完成 <strong>{summary.data?.active ?? '—'}</strong></span><span>我的待办 <strong>{summary.data?.mine ?? '—'}</strong></span></div>
  {summary.error && <p className="form-error">{summary.error}</p>}
  <div className="task-filters"><label>状态<select value={status} onChange={e=>filter(setStatus,e.target.value)}>{[['active','未完成'],['pending','待认领'],['in_progress','处理中'],['resolved','已完成'],['dismissed','已忽略'],['all','全部']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>异常类型<select value={kind} onChange={e=>filter(setKind,e.target.value)}><option value="">全部类型</option>{Object.entries(taskKinds).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label className="unread-filter"><input type="checkbox" checked={mine} onChange={e=>filter(setMine,e.target.checked)}/>只看我的待办</label></div>
  <div className="task-workspace"><aside className="panel task-list">{data.error || (data.loading && !data.data) ? <CatalogStatus {...data}/> : <>{data.data?.items.map(task=><button key={task.id} className={`staff-session ${params.get('task')===String(task.id) ? 'selected':''}`} onClick={()=>selectTask(task.id)}><strong>{task.priority==='high' ? '● ':''}{task.title}</strong><small>{task.order_number} · {taskStatuses[task.status]}</small><small>{task.assignee_name || '尚未认领'}</small></button>)}{data.data?.total===0 && <p>当前筛选下没有待办。</p>}<nav className="pagination"><button className="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page} / {data.data?.total_pages || 1}</span><button className="secondary" disabled={!data.data || page>=data.data.total_pages} onClick={()=>setPage(p=>p+1)}>下一页</button></nav></>}</aside>{params.get('task') ? <TaskDetail key={params.get('task')} id={params.get('task')} onChange={data.retry}/>:<section className="panel shop-empty">请选择一项待办，查看事实、分析与处理记录。</section>}</div>
 </>
}

export default function SupportTasks(){const auth=useAuth();return <ShopShell title="客服待办与订单异常" admin>{auth.isAdmin && <Workspace/>}</ShopShell>}
