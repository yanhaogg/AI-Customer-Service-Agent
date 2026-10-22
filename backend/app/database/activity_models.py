"""Private customer conversations and deduplicated product browsing history."""

from typing import Any

from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base
from . import models, catalog_models, shop_models


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("order_id", name="uq_chat_order"),)
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=True
    )
    order_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=True
    )
    context_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general", server_default="general"
    )
    human_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    staff_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index(
    "ix_chat_user_recent",
    ChatSession.user_id,
    ChatSession.updated_at.desc(),
    ChatSession.id.desc(),
)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "request_key", "role", name="uq_chat_message_request_role"
        ),
        CheckConstraint(
            "role IN ('user','assistant','human_agent')", name="ck_chat_message_role"
        ),
        CheckConstraint(
            "status IN ('pending','completed','failed')", name="ck_chat_message_status"
        ),
        Index("ix_chat_message_session_id", "session_id", "id"),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    staff_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BrowsingHistory(Base):
    __tablename__ = "product_browsing_history"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_browsing_user_product"),
        CheckConstraint("view_count > 0", name="ck_browsing_count"),
        Index("ix_browsing_user_recent", "user_id", "last_viewed_at"),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    image_asset_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media_assets.id"), nullable=True
    )
    first_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_visit_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ChatReadState(Base):
    __tablename__ = "chat_read_states"
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


ACTIVITY_TABLES = [
    model.__table__
    for model in (ChatSession, ChatMessage, BrowsingHistory, ChatReadState)
]
