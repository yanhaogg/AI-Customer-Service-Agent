"""Order-bound refund workflow, private evidence, reminders and audit events."""
from sqlalchemy import BigInteger,Boolean,CheckConstraint,Column,DateTime,ForeignKey,Identity,Index,Integer,Numeric,String,Text,UniqueConstraint,func,text
from .database import Base
from . import models,shop_models,activity_models


class RefundRequest(Base):
    __tablename__='refund_requests'
    __table_args__=(UniqueConstraint('user_id','request_key',name='uq_refund_user_request'),
        CheckConstraint("status IN ('review_pending','awaiting_return','return_in_transit','refunded','rejected','withdrawn')",name='ck_refund_status'),)
    id=Column(BigInteger,Identity(),primary_key=True)
    order_id=Column(BigInteger,ForeignKey('shop_orders.id'),nullable=False,index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    chat_session_id=Column(BigInteger,ForeignKey('chat_sessions.id',ondelete='SET NULL'))
    request_key=Column(String(64),nullable=False)
    request_hash=Column(String(64),nullable=False)
    reason=Column(String(30),nullable=False)
    description=Column(Text,nullable=False)
    contact_phone=Column(String(30),nullable=False)
    received=Column(Boolean,nullable=False)
    amount=Column(Numeric(14,2),nullable=False)
    currency=Column(String(3),nullable=False)
    status=Column(String(30),nullable=False)
    route_reason=Column(Text,nullable=False)
    original_status=Column(String(30),nullable=False)
    stock_restored=Column(Boolean,nullable=False,default=False)
    reviewer_id=Column(Integer,ForeignKey('users.id'))
    review_note=Column(Text)
    return_address=Column(Text)
    return_due_at=Column(DateTime(timezone=True))
    return_carrier=Column(String(100))
    return_tracking=Column(String(100))
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    updated_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    refunded_at=Column(DateTime(timezone=True))


Index('uq_refund_active_order',RefundRequest.order_id,unique=True,
      postgresql_where=text("status IN ('review_pending','awaiting_return','return_in_transit')"))
Index('uq_refund_success_order',RefundRequest.order_id,unique=True,postgresql_where=text("status = 'refunded'"))


class RefundEvidence(Base):
    __tablename__='refund_evidence'
    id=Column(BigInteger,Identity(),primary_key=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False,index=True)
    order_id=Column(BigInteger,ForeignKey('shop_orders.id'),nullable=False)
    refund_id=Column(BigInteger,ForeignKey('refund_requests.id'),index=True)
    storage_key=Column(Text,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())


class RefundEvent(Base):
    __tablename__='refund_events'
    id=Column(BigInteger,Identity(),primary_key=True)
    refund_id=Column(BigInteger,ForeignKey('refund_requests.id'),nullable=False,index=True)
    actor_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    action=Column(String(40),nullable=False)
    note=Column(Text,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())


class ShipmentReminder(Base):
    __tablename__='shipment_reminders'
    id=Column(BigInteger,Identity(),primary_key=True)
    order_id=Column(BigInteger,ForeignKey('shop_orders.id'),nullable=False,index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    note=Column(String(500),nullable=False)
    status=Column(String(20),nullable=False,default='pending')
    handled_note=Column(String(500))
    handled_at=Column(DateTime(timezone=True))
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())


AFTERSALES_TABLES=[m.__table__ for m in (RefundRequest,RefundEvidence,RefundEvent,ShipmentReminder)]
