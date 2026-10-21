import { useEffect,useRef } from 'react'
import { useAuth } from '../auth/useAuth'
import { shopRequest } from '../lib/shop'

export default function TrackProductView({productId}){
 const {token,user}=useAuth()
 const visitKey=useRef(crypto.randomUUID())
 const userId=user?.id
 useEffect(()=>{
  if(!userId || !token)return
  const controller=new AbortController()
  shopRequest(token,'/api/activity/browsing',{method:'POST',body:JSON.stringify({product_id:productId,visit_key:visitKey.current}),signal:controller.signal}).catch(()=>{})
  return ()=>controller.abort()
 },[token,userId,productId])
 return null
}
