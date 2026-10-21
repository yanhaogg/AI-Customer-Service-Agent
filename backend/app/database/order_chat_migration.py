"""Merge legacy per-intent order threads without discarding messages or refund links."""
from datetime import datetime,timezone
from hashlib import sha256
from sqlalchemy import delete,select,text,update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from .activity_models import ChatSession,ChatMessage,ChatReadState
from .aftersales_models import RefundRequest
from .shop_models import ShopOrder


def migrate_order_chats(connection):
    schema=(connection.get_execution_options().get('schema_translate_map') or {}).get(None)
    quote=connection.dialect.identifier_preparer.quote
    def table(name):return f'{quote(schema)}.{quote(name)}' if schema else quote(name)
    # All writers are blocked for the transaction; fail rather than disrupt an in-flight AI reply.
    connection.execute(text('LOCK TABLE '+', '.join(table(name) for name in ('shop_orders','chat_sessions','chat_messages','refund_requests','chat_read_states'))+' IN SHARE ROW EXCLUSIVE MODE'))
    merged=0;moved=0
    with Session(bind=connection) as db:
        rows=db.scalars(select(ChatSession).where(ChatSession.order_id.is_not(None)).order_by(ChatSession.order_id,ChatSession.id)).all()
        groups={}
        for row in rows:groups.setdefault(row.order_id,[]).append(row)
        for order_id,threads in groups.items():
            order=db.get(ShopOrder,order_id)
            if any(s.user_id!=order.user_id for s in threads):raise ValueError('Order conversation ownership mismatch')
            target=threads[0]
            if len(threads)>1:
                ids=[s.id for s in threads]
                if db.scalar(select(ChatMessage.id).where(ChatMessage.session_id.in_(ids),ChatMessage.status=='pending').limit(1)):
                    raise RuntimeError('An order reply is still pending; rerun after generation completes.')
                receipts=db.execute(select(ChatReadState.session_id,ChatReadState.user_id,ChatReadState.last_read_at).where(ChatReadState.session_id.in_(ids))).all()
                by_user={}
                for sid,uid,stamp in receipts:by_user.setdefault(uid,{})[sid]=stamp
                # One watermark cannot represent all formerly independent threads. Preserve all unread
                # messages conservatively, even if this makes some previously read messages unread again.
                for uid,stamps in by_user.items():
                    watermark=min(stamps.get(sid,datetime(1970,1,1,tzinfo=timezone.utc)) for sid in ids)
                    statement=insert(ChatReadState).values(session_id=target.id,user_id=uid,last_read_at=watermark)
                    db.execute(statement.on_conflict_do_update(index_elements=['session_id','user_id'],set_={'last_read_at':watermark}))
                for old in threads[1:]:
                    entries=db.scalars(select(ChatMessage).where(ChatMessage.session_id==old.id)).all()
                    for message in entries:
                        # Keep each original user/AI request pair together without key collisions.
                        message.request_key=sha256(f'order-merge:{old.id}:{message.request_key}'.encode()).hexdigest()
                        message.session_id=target.id
                    moved+=len(entries)
                    db.flush()
                    db.execute(update(RefundRequest).where(RefundRequest.chat_session_id==old.id).values(chat_session_id=target.id))
                newest=sorted(threads,key=lambda s:s.updated_at,reverse=True)
                handling=next((s for s in newest if s.human_status=='active'),None) or next((s for s in newest if s.human_status=='waiting'),None) or newest[0]
                target.human_status=handling.human_status;target.staff_user_id=handling.staff_user_id
                target.updated_at=max(s.updated_at for s in threads)
                target.product_id=target.product_id or next((s.product_id for s in newest if s.product_id),None)
                db.flush()
                db.execute(delete(ChatSession).where(ChatSession.id.in_(ids[1:])))
                merged+=len(threads)-1
            target.intent='general';target.title=f'订单咨询 · {order.number}';target.context_name=order.number
        db.flush()
    connection.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_order ON {table("chat_sessions")}(order_id)'))
    return {'merged_sessions':merged,'preserved_messages':moved}
