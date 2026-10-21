import { useEffect,useState } from 'react'
import { shopRequest } from '../lib/shop'
import { useAuth } from '../auth/useAuth'
import ChatText from './ChatText'

const pending=new Map()
function generate(token,id){
 const key=`${token}:${id}`
 if(!pending.has(key))pending.set(key,shopRequest(token,`/api/admin/support-sessions/${id}/assistant`,{method:'POST'}).finally(()=>pending.delete(key)))
 return pending.get(key)
}

export default function StaffAssistant({id,version,onUse,disabled,hasDraft}){
 const {token}=useAuth()
 const [state,setState]=useState({data:null,loading:true,error:''})
 useEffect(()=>{
  let active=true
  generate(token,id).then(data=>{if(active)setState({data,loading:false,error:''})})
   .catch(error=>{if(active)setState({data:null,loading:false,error:error.message})})
  return ()=>{active=false}
 },[token,id])
 async function refresh(){
  setState(previous=>({...previous,loading:true,error:''}))
  try{const data=await generate(token,id);setState({data,loading:false,error:''})}
  catch(error){setState(previous=>({...previous,loading:false,error:error.message}))}
 }
 const advice=state.data,stale=advice && advice.snapshot_version!==version
 return <section className="staff-assistant" aria-labelledby="staff-assistant-title" aria-busy={state.loading}>
  <div className="shop-toolbar"><h2 id="staff-assistant-title">人工客服助手</h2><button className="secondary" type="button" disabled={state.loading} onClick={refresh}>{state.loading ? '生成中…':'重新生成'}</button></div>
  <p className="muted">建议仅供接待参考，采用后可在下方回复框编辑，再手动发送。</p>
  {state.loading && <p role="status">正在整理聊天摘要、用户诉求和回复建议…</p>}
  {state.error && <p className="form-error" role="alert">{state.error}</p>}
  {advice && <>
   {stale && <p className="assistant-stale" role="status">会话已有更新，当前建议可能过期，请重新生成后核对。</p>}
   <div className="assistant-overview"><div><h3>聊天摘要</h3><ChatText text={advice.summary}/></div><div><h3>用户诉求</h3>{advice.customer_needs.length ? <ul>{advice.customer_needs.map((need,index)=><li key={index}>{need}</li>)}</ul>:<p>暂未识别到明确诉求。</p>}</div></div>
   <h3>建议回复</h3><ChatText text={advice.suggested_reply}/>
   <div className="assistant-footer"><small>基于最近 {advice.included_messages} 条消息{advice.has_older_messages ? '，未覆盖全部历史':''} · {new Date(advice.generated_at).toLocaleTimeString('zh-CN')}</small><button type="button" disabled={disabled || stale || state.loading} onClick={()=>onUse(advice.suggested_reply)}>{hasDraft ? '采用建议并替换回复草稿':'采用建议，填入回复框'}</button></div>
  </>}
 </section>
}
