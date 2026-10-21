"""Per-viewer read watermarks; loading a conversation never implicitly marks it read."""
from datetime import datetime,timezone
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,AwareDatetime
from sqlalchemy import and_,or_,func,select
from sqlalchemy.dialects.postgresql import insert
from app.database.activity_models import ChatMessage,ChatSession,ChatReadState


class ReadThrough(BaseModel):
    model_config=ConfigDict(extra='forbid')
    read_through:AwareDatetime


def unread_query(user,admin=False,session_ids=None):
    incoming=(or_(ChatMessage.role=='user',and_(ChatMessage.role=='human_agent',
        ChatMessage.staff_user_id.is_distinct_from(user.id))) if admin else ChatMessage.role.in_(['assistant','human_agent']))
    query=(select(ChatMessage.session_id,func.count().label('unread_count'))
        .join(ChatSession,ChatSession.id==ChatMessage.session_id)
        .outerjoin(ChatReadState,and_(ChatReadState.session_id==ChatMessage.session_id,ChatReadState.user_id==user.id))
        .where(incoming,ChatMessage.status!='pending',or_(ChatReadState.last_read_at.is_(None),ChatMessage.updated_at>ChatReadState.last_read_at)))
    if not admin:query=query.where(ChatSession.user_id==user.id)
    if session_ids is not None:query=query.where(ChatMessage.session_id.in_(session_ids))
    return query.group_by(ChatMessage.session_id)


def unread_counts(db,user,admin=False,session_ids=None):
    return dict(db.execute(unread_query(user,admin,session_ids)).all())


def read_through(entries):
    return max((m.updated_at for m in entries if m.status!='pending'),default=None)


def mark_read(db,user,session_id,body):
    if body.read_through>datetime.now(timezone.utc):raise HTTPException(422,'已读时间不能晚于当前时间')
    statement=insert(ChatReadState).values(session_id=session_id,user_id=user.id,last_read_at=body.read_through)
    db.execute(statement.on_conflict_do_update(index_elements=['session_id','user_id'],
        set_={'last_read_at':func.greatest(ChatReadState.last_read_at,statement.excluded.last_read_at)}))
    db.commit()
    return {'status':'read'}
