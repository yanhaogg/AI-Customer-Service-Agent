import base64
import binascii
import hashlib
import json
from datetime import timedelta
from io import BytesIO
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse
from PIL import Image,UnidentifiedImageError
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user,require_superadmin
from app.database.models import User
from app.database.session import get_db
from app.database.shop_models import ShopOrder
from app.database.aftersales_models import RefundRequest,RefundEvidence,RefundEvent,ShipmentReminder
from app.database.activity_models import ChatSession
from app.api.catalog import MATERIALS_ROOT
from app.services.aftersales import ACTIVE_REFUNDS,REASONS,now,refund_policy,auto_route,active_refund,order_session,event,complete_refund

router=APIRouter(prefix='/api/shop',tags=['order-aftersales'],dependencies=[Depends(get_current_user)])
admin_router=APIRouter(prefix='/api/admin',tags=['refund-review'],dependencies=[Depends(require_superadmin)])


class Body(BaseModel):model_config=ConfigDict(extra='forbid')
class Contact(Body):intent:Literal['general','human']='general'
class Reminder(Body):note:str=Field(default='请尽快安排发货，并告知预计发货时间。',max_length=500)
class RefundCreate(Body):
    request_key:str=Field(min_length=16,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    reason:Literal['not_needed','wrong_order','change_mind','not_received','quality','damaged','payment_issue','other']
    description:str=Field(min_length=10,max_length=2000)
    contact_phone:str=Field(min_length=6,max_length=30,pattern=r'^\+?[0-9 ()-]+$')
    received:bool
    evidence_ids:list[int]=Field(default_factory=list,max_length=3)
    @field_validator('description')
    @classmethod
    def description_nonblank(cls,value):
        if len(value.strip())<10:raise ValueError('情况说明至少10字')
        return value.strip()
    @field_validator('contact_phone')
    @classmethod
    def valid_phone(cls,value):
        if not 6<=sum(c.isdigit() for c in value)<=20:raise ValueError('请输入有效联系电话')
        return value
class EvidenceUpload(Body):data:str=Field(max_length=8_000_000)
class Review(Body):
    action:Literal['approve','reject','confirm_return']
    note:str=Field(min_length=5,max_length=1000)
    return_address:str=Field(default='',max_length=1000)
    @field_validator('note')
    @classmethod
    def note_nonblank(cls,value):
        if len(value.strip())<5:raise ValueError('处理说明至少5字')
        return value.strip()
class ReturnShipping(Body):
    carrier:str=Field(min_length=1,max_length=100)
    tracking_number:str=Field(min_length=3,max_length=100,pattern=r'^[A-Za-z0-9-]+$')
class HandleReminder(Body):note:str=Field(min_length=5,max_length=500)


def owned(db,user,order_id):
    order=db.scalar(select(ShopOrder).where(ShopOrder.id==order_id,ShopOrder.user_id==user.id).with_for_update())
    if order is None:raise HTTPException(404,'订单不存在')
    return order


def refund_data(db,refund):
    result={key:getattr(refund,key) for key in ('id','order_id','chat_session_id','reason','description','contact_phone','received',
        'currency','status','route_reason','original_status','review_note','return_address','return_due_at','return_carrier','return_tracking','created_at','refunded_at')}
    session=db.get(ChatSession,refund.chat_session_id) if refund.chat_session_id else None
    result.update(amount=str(refund.amount),demo=True,human_status=session.human_status if session else 'none',
        evidence=[{'id':e.id,'url':f'/api/shop/refund-evidence/{e.id}'} for e in db.scalars(select(RefundEvidence).where(RefundEvidence.refund_id==refund.id))],
        events=[{'action':e.action,'note':e.note,'created_at':e.created_at} for e in db.scalars(select(RefundEvent).where(RefundEvent.refund_id==refund.id).order_by(RefundEvent.id))])
    return result


@router.post('/orders/{order_id}/contact')
def contact(order_id:int,body:Contact,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order=owned(db,user,order_id);session=order_session(db,order,body.intent,human=body.intent=='human')
    result={'session_id':session.id,'order_id':order.id,'url':f'/chat?session={session.id}'};db.commit();return result


@router.post('/orders/{order_id}/remind-shipping')
def remind(order_id:int,body:Reminder,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order=owned(db,user,order_id)
    if order.status!='paid':raise HTTPException(409,'仅已支付且未发货的订单可以催发货')
    if active_refund(db,order.id):raise HTTPException(409,'售后处理中，暂不能催发货')
    previous=db.scalar(select(ShipmentReminder).where(ShipmentReminder.order_id==order.id).order_by(ShipmentReminder.id.desc()).limit(1))
    repeated=bool(previous and now()-previous.created_at<timedelta(hours=24))
    if not repeated:
        previous=ShipmentReminder(order_id=order.id,user_id=user.id,note=body.note,status='pending');db.add(previous);db.flush()
    session=order_session(db,order,'shipping_reminder')
    result={'id':previous.id,'repeated':repeated,'message':'24小时内已催促过，请耐心等待客服跟进。' if repeated else '催发货已记录，客服可在订单后台跟进。',
            'session_id':session.id,'url':f'/chat?session={session.id}'};db.commit();return result


@router.get('/orders/{order_id}/refund-options')
def options(order_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order=owned(db,user,order_id)
    result={**refund_policy(),'can_apply':order.status in ('paid','shipped','completed') and active_refund(db,order.id) is None,
            'auto_possible':auto_route(order,'not_needed',False),'order_status':order.status,
            'contact_phone':(order.shipping_address or {}).get('phone','')}
    db.commit();return result


@router.get('/orders/{order_id}/refunds')
def refunds(order_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order=owned(db,user,order_id)
    result={'items':[refund_data(db,r) for r in db.scalars(select(RefundRequest).where(RefundRequest.order_id==order.id).order_by(RefundRequest.id.desc()))]}
    db.commit();return result


@router.post('/orders/{order_id}/refunds',status_code=201)
def apply_refund(order_id:int,body:RefundCreate,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order=owned(db,user,order_id)
    fingerprint=hashlib.sha256(json.dumps({'order_id':order_id,**body.model_dump()},sort_keys=True).encode()).hexdigest()
    previous=db.scalar(select(RefundRequest).where(RefundRequest.user_id==user.id,RefundRequest.request_key==body.request_key))
    if previous:
        if previous.request_hash!=fingerprint:raise HTTPException(409,'重复请求编号对应不同申请，请重新填写')
        result=refund_data(db,previous);db.commit();return result
    if order.status not in ('paid','shipped','completed'):raise HTTPException(409,'仅已支付、已发货或已完成订单可以申请退款；待支付请取消订单')
    if active_refund(db,order.id):raise HTTPException(409,'该订单已有进行中的退款申请')
    if (order.status=='paid' and body.received) or (order.status=='completed' and not body.received):
        raise HTTPException(422,'收到货状态与当前订单不一致，请联系客服核实')
    if body.reason=='not_received' and body.received:raise HTTPException(422,'已收到货不能选择未收到货原因')
    if len(body.evidence_ids)!=len(set(body.evidence_ids)):raise HTTPException(422,'凭证不能重复')
    evidence=db.scalars(select(RefundEvidence).where(RefundEvidence.id.in_(body.evidence_ids),RefundEvidence.user_id==user.id,
        RefundEvidence.order_id==order.id,RefundEvidence.refund_id.is_(None)).with_for_update()).all()
    if len(evidence)!=len(body.evidence_ids):raise HTTPException(422,'部分凭证不属于本订单或已被使用')
    if body.reason in ('quality','damaged') and not evidence:raise HTTPException(422,'质量或破损问题请上传至少1张照片')
    automatic=auto_route(order,body.reason,body.received)
    session=order_session(db,order,'refund',human=not automatic)
    refund=RefundRequest(order_id=order.id,user_id=user.id,chat_session_id=session.id,request_key=body.request_key,request_hash=fingerprint,
        reason=body.reason,description=body.description,contact_phone=body.contact_phone,received=body.received,amount=order.total,
        currency=order.currency,status='review_pending',original_status=order.status,
        route_reason='未发货且支付24小时内的普通整单退款，自动处理' if automatic else '需要人工核验发货、收货、申请时效或异常原因')
    db.add(refund);db.flush()
    for e in evidence:e.refund_id=refund.id
    event(db,refund,user.id,'submitted',f'申请整单退款：{REASONS[body.reason]}')
    if automatic:complete_refund(db,order,refund,user.id,'符合自动退款规则')
    db.flush();result=refund_data(db,refund);db.commit();return result


@router.post('/orders/{order_id}/refund-evidence',status_code=201)
def upload_evidence(order_id:int,body:EvidenceUpload,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order=owned(db,user,order_id)
    if order.status not in ('paid','shipped','completed'):raise HTTPException(409,'该订单当前不可上传退款凭证')
    count=db.scalar(select(func.count()).select_from(RefundEvidence).where(RefundEvidence.user_id==user.id,RefundEvidence.created_at>=now()-timedelta(days=1)))
    if count>=30:raise HTTPException(429,'今天上传凭证较多，请稍后再试')
    try:
        raw=base64.b64decode(body.data,validate=True)
        if not raw or len(raw)>5_000_000:raise ValueError()
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>20_000_000:raise ValueError()
            image.load();output=BytesIO();image.convert('RGB').save(output,format='JPEG',quality=90)
        data=output.getvalue()
    except (ValueError,binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError):
        raise HTTPException(422,'请选择5MB内有效JPEG、PNG或WebP图片（最多2000万像素）') from None
    key=f'private_refund_evidence/{uuid4().hex}.jpg';path=MATERIALS_ROOT/key
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    entry=RefundEvidence(user_id=user.id,order_id=order.id,storage_key=key);db.add(entry);db.flush()
    result={'id':entry.id,'url':f'/api/shop/refund-evidence/{entry.id}'};db.commit();return result


@router.get('/refund-evidence/{evidence_id}')
def evidence_file(evidence_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    evidence=db.get(RefundEvidence,evidence_id)
    if evidence is None or not (evidence.user_id==user.id or (user.role=='super_admin' and evidence.refund_id is not None)):
        raise HTTPException(404,'凭证不存在')
    path=(MATERIALS_ROOT/evidence.storage_key).resolve()
    if not path.is_relative_to(MATERIALS_ROOT/'private_refund_evidence') or not path.is_file():raise HTTPException(404,'凭证文件不存在')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})


def locked_refund(db,refund_id,user=None):
    query=select(RefundRequest).where(RefundRequest.id==refund_id)
    if user:query=query.where(RefundRequest.user_id==user.id)
    refund=db.scalar(query)
    if refund is None:raise HTTPException(404,'退款申请不存在')
    order=db.scalar(select(ShopOrder).where(ShopOrder.id==refund.order_id).with_for_update())
    refund=db.scalar(query.with_for_update().execution_options(populate_existing=True))
    return order,refund


@router.post('/refunds/{refund_id}/withdraw')
def withdraw(refund_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order,refund=locked_refund(db,refund_id,user)
    if refund.status not in ('review_pending','awaiting_return'):raise HTTPException(409,'当前阶段不能撤销，请联系人工客服')
    refund.status='withdrawn';event(db,refund,user.id,'withdrawn','用户撤销退款申请')
    db.flush();result=refund_data(db,refund);db.commit();return result


@router.post('/refunds/{refund_id}/return-shipping')
def return_shipping(refund_id:int,body:ReturnShipping,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    order,refund=locked_refund(db,refund_id,user)
    if refund.status!='awaiting_return':raise HTTPException(409,'请先等待客服审核并提供退货地址')
    if not body.carrier.strip():raise HTTPException(422,'快递公司不能为空')
    refund.status='return_in_transit';refund.return_carrier=body.carrier.strip();refund.return_tracking=body.tracking_number
    event(db,refund,user.id,'return_shipped','用户提交退货物流，等待客服验收')
    db.flush();result=refund_data(db,refund);db.commit();return result


@admin_router.post('/refunds/{refund_id}/review')
def review(refund_id:int,body:Review,db:Session=Depends(get_db),user:User=Depends(require_superadmin)):
    order,refund=locked_refund(db,refund_id)
    if refund.status=='refunded' and body.action in ('approve','confirm_return'):
        result=refund_data(db,refund);db.commit();return result
    if body.action=='reject':
        if refund.status!='review_pending':raise HTTPException(409,'仅待审核申请可以驳回')
        refund.status='rejected';event(db,refund,user.id,'rejected',body.note)
    elif body.action=='approve':
        if refund.status!='review_pending':raise HTTPException(409,'该申请不在待审核阶段')
        if refund.received and refund.original_status in ('shipped','completed'):
            if len(body.return_address.strip())<10:raise HTTPException(422,'请填写至少10字的完整退货地址和联系人')
            refund.status='awaiting_return';refund.return_address=body.return_address.strip();refund.return_due_at=now()+timedelta(days=7)
            event(db,refund,user.id,'return_authorized',body.note)
        else:complete_refund(db,order,refund,user.id,body.note)
    else:
        if refund.status!='return_in_transit':raise HTTPException(409,'仅已寄回的申请可以确认验收退款')
        complete_refund(db,order,refund,user.id,'客服确认退货验收：'+body.note)
    refund.reviewer_id=user.id;refund.review_note=body.note
    db.flush();result=refund_data(db,refund);db.commit();return result


@admin_router.post('/reminders/{reminder_id}/handle')
def handle_reminder(reminder_id:int,body:HandleReminder,db:Session=Depends(get_db)):
    reminder=db.get(ShipmentReminder,reminder_id)
    if reminder is None:raise HTTPException(404,'催发货记录不存在')
    db.execute(select(ShopOrder.id).where(ShopOrder.id==reminder.order_id).with_for_update())
    reminder.status='handled';reminder.handled_note=body.note;reminder.handled_at=now();db.commit();return {'status':'handled'}


@admin_router.get('/orders/{order_id}/refunds')
def admin_refunds(order_id:int,db:Session=Depends(get_db)):
    if db.get(ShopOrder,order_id) is None:raise HTTPException(404,'订单不存在')
    return {'items':[refund_data(db,r) for r in db.scalars(select(RefundRequest).where(RefundRequest.order_id==order_id).order_by(RefundRequest.id.desc()))]}
