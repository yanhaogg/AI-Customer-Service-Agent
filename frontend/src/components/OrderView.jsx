import { useState } from 'react'
import { Link,useNavigate } from 'react-router-dom'
import CatalogImage from './CatalogImage'
import AftersalesPanel from './AftersalesPanel'
import { refundLabels } from '../lib/refunds'
import { useAuth } from '../auth/useAuth'
import { money,shopRequest,statuses } from '../lib/shop'

export default function OrderView({order,admin=false,onChange}){
 const {token}=useAuth(),navigate=useNavigate()
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[shipping,setShipping]=useState(false),[carrier,setCarrier]=useState(''),[tracking,setTracking]=useState('')
 const [aftersales,setAftersales]=useState(false),[handling,setHandling]=useState(false),[handleNote,setHandleNote]=useState('')
 const refund=order.aftersales?.refund,reminder=order.aftersales?.reminder
 const refundActive=refund && ['review_pending','awaiting_return','return_in_transit'].includes(refund.status)
 async function run(path,body){return shopRequest(token,path,{method:'POST',...(body ? {body:JSON.stringify(body)}:{})})}
 async function act(action){
  setBusy(true);setError('')
  try{await run(`/api/shop/orders/${order.id}/${action}`);onChange()}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function contact(){
  setBusy(true);setError('')
  try{const result=await run(`/api/shop/orders/${order.id}/contact`,{intent:'general'});navigate(result.url)}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function remind(){
  setBusy(true);setError('')
  try{const result=await run(`/api/shop/orders/${order.id}/remind-shipping`,{});setNotice(result.message)}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function ship(event){
  event.preventDefault();setBusy(true);setError('')
  try{await run(`/api/admin/orders/${order.id}/ship`,{carrier,tracking_number:tracking});setShipping(false);onChange()}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function handle(event){
  event.preventDefault();setBusy(true);setError('')
  try{await run(`/api/admin/reminders/${reminder.id}/handle`,{note:handleNote});setHandling(false);onChange()}catch(err){setError(err.message)}finally{setBusy(false)}
 }
 const a=order.shipping_address
 return <article className="panel shop-order">
  <div className="order-top"><div><Link to={admin ? '/admin/orders':`/orders/${order.id}`}><strong>{order.number}</strong></Link><small>{new Date(order.created_at).toLocaleString('zh-CN')}{admin ? ` · 用户 #${order.user_id}`:''}</small></div><span className="pill">{statuses[order.status]}</span></div>
  {order.items.map((item,index)=><div className="cart-row" key={index}><CatalogImage product={item}/><div className="cart-description"><Link to={`/products/${item.product_id}`}>{item.name}</Link><small>{money(item.unit_price,order.currency)} × {item.quantity}</small></div><strong>{money(item.subtotal,order.currency)}</strong></div>)}
  <div className="order-information"><p><strong>收货人：</strong>{a.recipient} · {a.phone}</p><p><strong>收货地址：</strong>{a.region} {a.detail} {a.postal_code}</p>{order.note && <p><strong>备注：</strong>{order.note}</p>}{order.tracking_number && <p><strong>物流：</strong>{order.carrier} · {order.tracking_number}</p>}{order.status==='pending_payment' && <p>请于 {new Date(order.expires_at).toLocaleString('zh-CN')} 前完成模拟支付。</p>}{order.cancel_reason && <p>取消原因：{order.cancel_reason}</p>}{refund && <p className="aftersales-state">退款售后：{refundLabels[refund.status]} · {refund.route_reason}</p>}{reminder && <p>催发货：{new Date(reminder.created_at).toLocaleString('zh-CN')} · {reminder.status==='pending' ? '待客服跟进':reminder.handled_note || '已跟进'}</p>}</div>
  {error && <p role="alert" className="form-error">{error}</p>}{notice && <p role="status" className="success-note">{notice}</p>}
  <div className="checkout-bar"><strong>订单合计 {money(order.total,order.currency)}</strong><div className="management-actions">{!admin && <>
   {order.status==='pending_payment' && <><button disabled={busy} onClick={()=>act('pay')}>模拟支付</button><button className="secondary" disabled={busy} onClick={()=>act('cancel')}>取消订单</button></>}
   {order.status==='shipped' && <button disabled={busy || refundActive} onClick={()=>act('complete')}>确认收货</button>}
   <button className="secondary" disabled={busy} onClick={contact}>联系客服</button>
   {order.status==='paid' && <button className="secondary" disabled={busy || refundActive} onClick={remind}>催发货</button>}
  </>}{(refund || ['paid','shipped','completed'].includes(order.status)) && <button className="secondary" disabled={busy} onClick={()=>setAftersales(value=>!value)}>{admin ? '处理/查看售后':refund ? '查看/申请售后':'申请退款'}</button>}
   {admin && <Link to={`/admin/tasks?order=${order.id}`}>分析订单 / 查看待办 →</Link>}{admin && order.status==='paid' && <button disabled={busy || refundActive} onClick={()=>setShipping(true)}>录入物流并发货</button>}
   {admin && reminder?.status==='pending' && <button className="secondary" disabled={busy} onClick={()=>setHandling(true)}>跟进催发货</button>}
  </div></div>
  {shipping && <form className="shipping-form" onSubmit={ship}><label>快递公司<input required maxLength={100} value={carrier} onChange={e=>setCarrier(e.target.value)}/></label><label>快递单号<input required minLength={3} maxLength={100} pattern="[a-zA-Z0-9-]+" value={tracking} onChange={e=>setTracking(e.target.value)}/></label><button disabled={busy || refundActive}>确认发货</button><button type="button" className="secondary" disabled={busy} onClick={()=>setShipping(false)}>取消</button></form>}
  {handling && <form className="shipping-form" onSubmit={handle}><label>跟进说明<input required minLength={5} maxLength={500} value={handleNote} onChange={e=>setHandleNote(e.target.value)} placeholder="说明预计发货时间或跟进结果"/></label><button disabled={busy}>保存跟进结果</button></form>}
  {aftersales && <AftersalesPanel order={order} admin={admin} onChanged={onChange} onClose={()=>setAftersales(false)}/>}
 </article>
}
