"""Private customer conversations and deduplicated product browsing history."""
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base
from . import models, catalog_models, shop_models


class ChatSession(Base):
    __tablename__ = 'chat_sessions'
    __table_args__ = (UniqueConstraint('order_id',name='uq_chat_order'),)
    id = Column(BigInteger, Identity(), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(100), nullable=False)
    product_id = Column(BigInteger, ForeignKey('products.id'))
    order_id = Column(BigInteger, ForeignKey('shop_orders.id'))
    context_name = Column(Text)
    intent = Column(String(30),nullable=False,default='general',server_default='general')
    human_status = Column(String(20),nullable=False,default='none',server_default='none')
    staff_user_id = Column(Integer,ForeignKey('users.id'))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index('ix_chat_user_recent', ChatSession.user_id, ChatSession.updated_at.desc(), ChatSession.id.desc())


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    __table_args__ = (
        UniqueConstraint('session_id','request_key','role',name='uq_chat_message_request_role'),
        CheckConstraint("role IN ('user','assistant','human_agent')",name='ck_chat_message_role'),
        CheckConstraint("status IN ('pending','completed','failed')",name='ck_chat_message_status'),
        Index('ix_chat_message_session_id', 'session_id','id'),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    session_id = Column(BigInteger, ForeignKey('chat_sessions.id',ondelete='CASCADE'), nullable=False)
    request_key = Column(String(64), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    agent_metadata = Column(JSONB, nullable=False, default=dict, server_default='{}')
    staff_user_id = Column(Integer,ForeignKey('users.id'))
    status = Column(String(20), nullable=False, default='completed')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BrowsingHistory(Base):
    __tablename__ = 'product_browsing_history'
    __table_args__ = (
        UniqueConstraint('user_id','product_id',name='uq_browsing_user_product'),
        CheckConstraint('view_count > 0',name='ck_browsing_count'),
        Index('ix_browsing_user_recent','user_id','last_viewed_at'),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    product_id = Column(BigInteger, ForeignKey('products.id'), nullable=False)
    product_name = Column(Text, nullable=False)
    image_asset_id = Column(BigInteger, ForeignKey('media_assets.id'))
    first_viewed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_viewed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    view_count = Column(Integer, nullable=False, default=1)
    last_visit_key = Column(String(64), nullable=False)


class ChatReadState(Base):
    __tablename__ = 'chat_read_states'
    session_id = Column(BigInteger, ForeignKey('chat_sessions.id',ondelete='CASCADE'), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id',ondelete='CASCADE'), primary_key=True)
    last_read_at = Column(DateTime(timezone=True), nullable=False)


ACTIVITY_TABLES = [model.__table__ for model in (ChatSession,ChatMessage,BrowsingHistory,ChatReadState)]
