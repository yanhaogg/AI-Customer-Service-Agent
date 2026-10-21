"""Authenticated customer history. Never accept user identity or assistant text from clients."""
import logging
from datetime import datetime,timedelta,timezone
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator
from sqlalchemy import delete,func,select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.database.models import User
from app.database.catalog_models import Product,ProductImage
from app.database.shop_models import ShopOrder
from app.database.activity_models import BrowsingHistory,ChatMessage,ChatSession
from app.api.catalog import VISIBLE_STATUSES,product_query,serialize_products
from app.agent.graph import support_agent
from app.agent.config import load_settings,AgentConfigurationError,AgentUnavailableError
from app.services.chat_unread import ReadThrough,unread_counts,read_through,mark_read

logger=logging.getLogger(__name__)
router=APIRouter(prefix='/api/activity',tags=['customer-history'],dependencies=[Depends(get_current_user)])
PositiveId=Annotated[StrictInt,Field(gt=0)]


class StrictBody(BaseModel):
    model_config=ConfigDict(extra='forbid')


class SessionCreate(StrictBody):
    title: str=Field(default='新的咨询',min_length=1,max_length=100)
    product_id: PositiveId | None=None
    order_number: str | None=Field(default=None,min_length=1,max_length=40)

    @field_validator('title')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('标题不能为空')
        return value.strip()


class MessageCreate(StrictBody):
    content: str=Field(min_length=1,max_length=10000)
    request_key: str=Field(min_length=16,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')

    @field_validator('content')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('消息不能为空')
        return value.strip()


class BrowseCreate(StrictBody):
    product_id: PositiveId
    visit_key: str=Field(min_length=16,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')


def now():return datetime.now(timezone.utc)


def lock_user(db,user):
    db.execute(select(User.id).where(User.id==user.id).with_for_update())


def owned_session(db,user,session_id,lock=False):
    query=select(ChatSession).where(ChatSession.id==session_id,ChatSession.user_id==user.id)
    if lock:query=query.with_for_update()
    session=db.scalar(query)
    if session is None:raise HTTPException(404,'会话不存在')
    return session


def session_data(session):
    return {key:getattr(session,key) for key in ('id','title','product_id','order_id','context_name','created_at','updated_at','intent','human_status')}


def message_data(message):
    return {key:getattr(message,key) for key in ('id','role','content','status','request_key','created_at','agent_metadata')}


@router.get('/agent-status')
def agent_status():
    try:
        settings=load_settings()
        return {'configured':True,'model':settings.model,'mode':'manager_multi_agent','agents':['product_agent','order_agent','aftersales_agent']}
    except AgentConfigurationError as error:
        return {'configured':False,'model':None,'mode':'manager_multi_agent','message':str(error)}


def recover_interrupted(db,session_id):
    entries=db.scalars(select(ChatMessage).where(ChatMessage.session_id==session_id,
        ChatMessage.status=='pending',ChatMessage.updated_at<now()-timedelta(minutes=2))).all()
    for entry in entries:
        entry.status='failed';entry.content='回复中断，可点击重试。';entry.updated_at=now()
    db.flush()


@router.post('/sessions',status_code=201)
def create_session(body:SessionCreate,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    lock_user(db,user)
    context=[];order_id=None
    if body.product_id:
        product=db.scalar(select(Product).where(Product.id==body.product_id,Product.status.in_(VISIBLE_STATUSES)))
        if product is None:raise HTTPException(404,'商品不存在或已删除')
        context.append(product.name_zh or product.name_original)
    if body.order_number:
        order=db.scalar(select(ShopOrder).where(ShopOrder.number==body.order_number,ShopOrder.user_id==user.id).with_for_update())
        if order is None:raise HTTPException(404,'订单不存在')
        from app.services.aftersales import order_session
        existing=db.scalar(select(ChatSession.id).where(ChatSession.order_id==order.id))
        if existing is None and db.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.user_id==user.id))>=500:
            raise HTTPException(422,'最多保存 500 个会话，请先删除不需要的记录')
        session=order_session(db,order)
        if session.product_id is None and body.product_id:session.product_id=body.product_id
        db.flush()
        result=session_data(session);db.commit();return result
    if db.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.user_id==user.id))>=500:
        raise HTTPException(422,'最多保存 500 个会话，请先删除不需要的记录')
    session=ChatSession(user_id=user.id,title=body.title,product_id=body.product_id,order_id=order_id,context_name=' / '.join(context) or None)
    db.add(session);db.flush();result=session_data(session);db.commit();return result


@router.get('/sessions')
def sessions(page:int=Query(1,ge=1),q:str=Query('',max_length=100),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    query=select(ChatSession).where(ChatSession.user_id==user.id)
    if q.strip():query=query.where(ChatSession.title.icontains(q.strip(),autoescape=True))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(ChatSession.updated_at.desc(),ChatSession.id.desc()).offset((page-1)*20).limit(20)).all()
    counts=unread_counts(db,user,session_ids=[s.id for s in rows])
    return {'items':[{**session_data(s),'unread_count':counts.get(s.id,0)} for s in rows],'total':total,'total_pages':(total+19)//20}


@router.get('/unread')
def unread(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    counts=unread_counts(db,user)
    return {'total':sum(counts.values()),'sessions':counts}


@router.post('/sessions/{session_id}/read')
def read_session(session_id:int,body:ReadThrough,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    owned_session(db,user,session_id)
    return mark_read(db,user,session_id,body)


@router.get('/sessions/{session_id}')
def messages(session_id:int,before_id:int|None=Query(None,gt=0),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    session=owned_session(db,user,session_id,lock=True);recover_interrupted(db,session_id)
    query=select(ChatMessage).where(ChatMessage.session_id==session_id)
    if before_id:query=query.where(ChatMessage.id<before_id)
    entries=db.scalars(query.order_by(ChatMessage.id.desc()).limit(51)).all()
    result={'session':session_data(session),'items':[message_data(m) for m in reversed(entries[:50])],'has_more':len(entries)>50,'read_through':read_through(entries[:50])}
    db.commit();return result


@router.delete('/sessions/{session_id}',status_code=204)
def delete_session(session_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    session=owned_session(db,user,session_id,lock=True);db.delete(session);db.commit()


@router.post('/sessions/{session_id}/messages')
def send_message(session_id:int,body:MessageCreate,response:Response,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    session=owned_session(db,user,session_id,lock=True);recover_interrupted(db,session_id)
    existing=db.scalars(select(ChatMessage).where(ChatMessage.session_id==session_id,ChatMessage.request_key==body.request_key)).all()
    previous={m.role:m for m in existing}
    if existing:
        if previous['user'].content!=body.content:raise HTTPException(409,'该请求编号已用于另一条消息')
        assistant=previous['assistant']
        if assistant.status!='failed':
            response.status_code=202 if assistant.status=='pending' else 200
            result={'items':[message_data(previous['user']),message_data(assistant)]};db.commit();return result
    if db.scalar(select(ChatMessage.id).where(ChatMessage.session_id==session_id,ChatMessage.status=='pending').limit(1)):
        raise HTTPException(409,'上一条消息正在回复，请稍候')
    if not existing:
        if db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id==session_id))>=2000:
            raise HTTPException(422,'当前会话消息较多，请新建会话继续咨询')
        user_message=ChatMessage(session_id=session_id,request_key=body.request_key,role='user',content=body.content,status='completed')
        assistant=ChatMessage(session_id=session_id,request_key=body.request_key,role='assistant',content='',status='pending')
        db.add_all([user_message,assistant]);db.flush()
        previous['user']=user_message
    else:
        assistant.status='pending';assistant.content='';assistant.updated_at=now()
    session.updated_at=now()
    generation_started=now()
    assistant.updated_at=generation_started
    if session.human_status in ('waiting','active'):
        assistant.status='completed';assistant.content='消息已送达人工客服，请等待客服回复。'
        assistant.agent_metadata={'mode':'human_handoff'}
        db.flush();result={'items':[message_data(previous['user']),message_data(assistant)]};db.commit();return result
    assistant_id=assistant.id
    order=db.get(ShopOrder,session.order_id) if session.order_id else None
    order_number=order.number if order else ''
    product_id=session.product_id
    verified_user_id=user.id
    current_message_id=previous['user'].id
    database_bind=db.get_bind()
    history=[{'role':m.role,'content':m.content} for m in reversed(db.scalars(select(ChatMessage).where(
        ChatMessage.session_id==session_id,ChatMessage.status=='completed',ChatMessage.id<=current_message_id)
        .order_by(ChatMessage.id.desc()).limit(20)).all())]
    # Persist the user message before invoking any agent. No DB locks during generation.
    db.commit()
    try:
        result=support_agent.invoke({'user_input':body.content,'user_id':verified_user_id,'order_id':order_number,
                                  'product_id':product_id,'current_message_id':current_message_id,
                                  'session_factory':lambda:Session(bind=database_bind),'conversation_history':history})
        answer=result.get('answer')
        if not isinstance(answer,str) or not answer.strip():raise ValueError('Empty assistant response')
        status='completed';metadata=result.get('agent_metadata',{})
    except (AgentConfigurationError,AgentUnavailableError) as error:
        answer=str(error);status='failed';metadata={}
    except Exception:
        logger.warning('Chat generation failed for message %s',assistant_id)
        answer='客服模型暂时无法回复，你的消息已保存，请稍后重试。';status='failed';metadata={}
    session=owned_session(db,user,session_id,lock=True)
    # A timeout recovery/retry must never be overwritten by a late original response.
    assistant=db.scalar(select(ChatMessage).where(ChatMessage.id==assistant_id).execution_options(populate_existing=True))
    if assistant.status=='pending' and assistant.updated_at==generation_started:
        assistant.content=answer;assistant.status=status;assistant.updated_at=now();session.updated_at=now()
        assistant.agent_metadata=metadata
    db.flush()
    result={'items':[message_data(previous['user']),message_data(assistant)]};db.commit();return result


@router.post('/browsing')
def record_browse(body:BrowseCreate,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    lock_user(db,user)
    product=db.scalar(select(Product).where(Product.id==body.product_id,Product.status.in_(VISIBLE_STATUSES)))
    if product is None:raise HTTPException(404,'商品不存在或已删除')
    image=db.scalar(select(ProductImage.asset_id).where(ProductImage.product_id==product.id)
                    .order_by(ProductImage.is_primary.desc(),ProductImage.sort_order,ProductImage.id).limit(1))
    entry=db.scalar(select(BrowsingHistory).where(BrowsingHistory.user_id==user.id,BrowsingHistory.product_id==product.id))
    if entry is None:
        entry=BrowsingHistory(user_id=user.id,product_id=product.id,product_name=product.name_zh or product.name_original,
                              image_asset_id=image,view_count=1,last_visit_key=body.visit_key)
        db.add(entry)
    elif entry.last_visit_key!=body.visit_key:
        entry.view_count+=1;entry.last_visit_key=body.visit_key;entry.last_viewed_at=now()
    entry.product_name=product.name_zh or product.name_original;entry.image_asset_id=image
    db.flush()
    # Keep the most recent 500 distinct products per user.
    stale=select(BrowsingHistory.id).where(BrowsingHistory.user_id==user.id).order_by(BrowsingHistory.last_viewed_at.desc(),BrowsingHistory.id.desc()).offset(500)
    db.execute(delete(BrowsingHistory).where(BrowsingHistory.id.in_(stale)))
    result={'id':entry.id,'view_count':entry.view_count};db.commit();return result


@router.get('/browsing')
def browsing(page:int=Query(1,ge=1),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    query=select(BrowsingHistory).where(BrowsingHistory.user_id==user.id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(BrowsingHistory.last_viewed_at.desc(),BrowsingHistory.id.desc()).offset((page-1)*20).limit(20)).all()
    products={p['id']:p for p in serialize_products(db,db.execute(product_query().where(Product.id.in_([r.product_id for r in rows]))).all())}
    return {'items':[{'id':r.id,'product_id':r.product_id,'name':r.product_name,'view_count':r.view_count,
            'last_viewed_at':r.last_viewed_at,'available':r.product_id in products,
            'product':products.get(r.product_id),'image':{'url':f'/api/catalog/media/{r.image_asset_id}'} if r.image_asset_id else None} for r in rows],
            'total':total,'total_pages':(total+19)//20}


@router.delete('/browsing',status_code=204)
def clear_browsing(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    lock_user(db,user);db.execute(delete(BrowsingHistory).where(BrowsingHistory.user_id==user.id));db.commit()


@router.delete('/browsing/{entry_id}',status_code=204)
def delete_browse(entry_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    lock_user(db,user)
    entry=db.scalar(select(BrowsingHistory).where(BrowsingHistory.id==entry_id,BrowsingHistory.user_id==user.id))
    if entry is None:raise HTTPException(404,'浏览记录不存在')
    db.delete(entry);db.commit()
