import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { apiUrl } from './catalog'

export async function shopRequest(token,path,options={}) {
 const response=await fetch(apiUrl(path),{...options,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json',...options.headers}})
 const body=response.status===204 ? null : await response.json()
 if(!response.ok)throw new Error(typeof body?.detail==='string' ? body.detail : '请检查填写的信息和商品数量，再试一次。')
 return body
}
export function useShop(path,{keepPrevious=false}={}){
 const {token}=useAuth()
 const [attempt,setAttempt]=useState(0),[state,setState]=useState({key:'',data:null,error:''})
 const retry=useCallback(()=>setAttempt(n=>n+1),[])
 const identity=`${token}:${path}`
 const key=`${identity}:${attempt}`
 useEffect(()=>{
  if(!token || !path)return
  const controller=new AbortController()
  shopRequest(token,path,{signal:controller.signal})
   .then(data=>{if(!controller.signal.aborted)setState({key,identity,data,error:''})})
   .catch(error=>{if(!controller.signal.aborted)setState({key,identity,data:null,error:error.message})})
  return ()=>controller.abort()
 },[token,path,key,identity])
 return {data:state.key===key || (keepPrevious && state.identity===identity) ? state.data : null,error:state.key===key ? state.error : '',loading:!!token && !!path && state.key!==key,retry}
}
export const statuses={pending_payment:'待支付',paid:'待发货',shipped:'待收货',completed:'已完成',cancelled:'已取消',refunded:'已退款（模拟）'}
export function money(amount,currency){return new Intl.NumberFormat('zh-CN',{style:'currency',currency}).format(Number(amount))}
