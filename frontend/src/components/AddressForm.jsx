import { useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { shopRequest } from '../lib/shop'

export default function AddressForm({address,onSaved,onCancel}){
 const {token}=useAuth()
 const [form,setForm]=useState(address || {recipient:'',phone:'',region:'',detail:'',postal_code:'',is_default:false})
 const [busy,setBusy]=useState(false),[error,setError]=useState('')
 function change(key,value){setForm(old=>({...old,[key]:value}))}
 async function save(event){
  event.preventDefault();setBusy(true);setError('')
  try{
   const {recipient,phone,region,detail,postal_code,is_default}=form
   const result=await shopRequest(token,`/api/shop/addresses${address ? `/${address.id}` : ''}`,{method:address ? 'PUT':'POST',body:JSON.stringify({recipient,phone,region,detail,postal_code,is_default})})
   onSaved(result)
  }catch(err){setError(err.message)}finally{setBusy(false)}
 }
 return <form className="address-form" onSubmit={save}>{error && <p className="form-error" role="alert">{error}</p>}<fieldset disabled={busy}><div className="product-form-grid">
  <label>收货人 *<input required maxLength={80} autoComplete="name" value={form.recipient} onChange={e=>change('recipient',e.target.value)}/></label>
  <label>联系电话 *<input required type="tel" minLength={6} maxLength={30} autoComplete="tel" value={form.phone} onChange={e=>change('phone',e.target.value)} placeholder="手机号或包含区号的联系电话"/></label>
  <label className="full-width">省 / 市 / 区 *<input required minLength={2} maxLength={200} value={form.region} onChange={e=>change('region',e.target.value)} placeholder="例如：广东省 深圳市 南山区"/></label>
  <label className="full-width">详细地址 *<input required minLength={3} maxLength={500} autoComplete="street-address" value={form.detail} onChange={e=>change('detail',e.target.value)} placeholder="街道、小区、楼栋、门牌号"/></label>
  <label>邮政编码<input maxLength={20} autoComplete="postal-code" value={form.postal_code} onChange={e=>change('postal_code',e.target.value)}/></label>
 </div><label className="check-line"><input type="checkbox" checked={form.is_default} onChange={e=>change('is_default',e.target.checked)}/>设为默认地址</label><div className="management-actions"><button>{busy ? '保存中…':'保存地址'}</button><button type="button" className="secondary" onClick={onCancel}>取消</button></div></fieldset></form>
}
