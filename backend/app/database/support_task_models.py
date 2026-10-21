"""Internal, deduplicated order follow-up tasks and auditable staff actions."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
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
from . import models, shop_models


class SupportTask(Base):
    __tablename__ = "support_tasks"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "kind", "source_key", name="uq_support_task_source"
        ),
        CheckConstraint(
            "status IN ('pending','in_progress','resolved','dismissed')",
            name="ck_support_task_status",
        ),
        CheckConstraint(
            "kind IN ('shipping_overdue','receipt_overdue','refund_overdue')",
            name="ck_support_task_kind",
        ),
        CheckConstraint(
            "analysis_status IN ('pending','generating','ready','failed')",
            name="ck_task_analysis_status",
        ),
        Index("ix_support_tasks_queue", "status", "due_at", "id"),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    order_id = Column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    kind = Column(String(30), nullable=False)
    source_key = Column(String(80), nullable=False)
    title = Column(String(160), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    priority = Column(String(10), nullable=False, default="normal")
    assignee_id = Column(Integer, ForeignKey("users.id"))
    due_at = Column(DateTime(timezone=True), nullable=False)
    snapshot = Column(JSONB, nullable=False, default=dict)
    snapshot_version = Column(String(64), nullable=False)
    advice = Column(JSONB, nullable=False, default=dict)
    advice_version = Column(String(64))
    analysis_status = Column(String(20), nullable=False, default="pending")
    analysis_key = Column(String(32))
    analysis_started_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True))
    resolution_note = Column(Text)


class SupportTaskEvent(Base):
    __tablename__ = "support_task_events"
    id = Column(BigInteger, Identity(), primary_key=True)
    task_id = Column(
        BigInteger,
        ForeignKey("support_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(30), nullable=False)
    note = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupportScanState(Base):
    __tablename__ = "support_scan_state"
    id = Column(Integer, primary_key=True)
    scanned_at = Column(DateTime(timezone=True), nullable=False)
    result = Column(JSONB, nullable=False)


class SupportTaskPreview(Base):
    __tablename__ = "support_task_previews"
    id = Column(String(32), primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(BigInteger, ForeignKey("shop_orders.id"), nullable=False)
    kind = Column(String(30), nullable=False)
    source_key = Column(String(80), nullable=False)
    snapshot = Column(JSONB, nullable=False)
    snapshot_version = Column(String(64), nullable=False)
    advice = Column(JSONB, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


SUPPORT_TASK_TABLES = [
    model.__table__
    for model in (SupportTask, SupportTaskEvent, SupportScanState, SupportTaskPreview)
]
