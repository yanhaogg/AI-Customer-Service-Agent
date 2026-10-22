"""Order-bound refund workflow, private evidence, reminders and audit events."""

from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from .database import Base
from . import models, shop_models, activity_models


class RefundRequest(Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_refund_user_request"),
        CheckConstraint(
            "status IN ('review_pending','awaiting_return','return_in_transit','refunded','rejected','withdrawn')",
            name="ck_refund_status",
        ),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    chat_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    received: Mapped[bool] = mapped_column(Boolean, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    route_reason: Mapped[str] = mapped_column(Text, nullable=False)
    original_status: Mapped[str] = mapped_column(String(30), nullable=False)
    stock_restored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    return_carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    return_tracking: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


Index(
    "uq_refund_active_order",
    RefundRequest.order_id,
    unique=True,
    postgresql_where=text(
        "status IN ('review_pending','awaiting_return','return_in_transit')"
    ),
)
Index(
    "uq_refund_success_order",
    RefundRequest.order_id,
    unique=True,
    postgresql_where=text("status = 'refunded'"),
)


class RefundEvidence(Base):
    __tablename__ = "refund_evidence"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False
    )
    refund_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("refund_requests.id"), index=True, nullable=True
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RefundEvent(Base):
    __tablename__ = "refund_events"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    refund_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("refund_requests.id"), nullable=False, index=True
    )
    actor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ShipmentReminder(Base):
    __tablename__ = "shipment_reminders"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    note: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    handled_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


AFTERSALES_TABLES = [
    m.__table__ for m in (RefundRequest, RefundEvidence, RefundEvent, ShipmentReminder)
]
