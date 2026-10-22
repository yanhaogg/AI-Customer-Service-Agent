"""Internal, deduplicated order follow-up tasks and auditable staff actions."""

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
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    assignee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
    advice: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    advice_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    analysis_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    analysis_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupportTaskEvent(Base):
    __tablename__ = "support_task_events"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupportScanState(Base):
    __tablename__ = "support_scan_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class SupportTaskPreview(Base):
    __tablename__ = "support_task_previews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)
    actor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
    advice: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


SUPPORT_TASK_TABLES = [
    model.__table__
    for model in (SupportTask, SupportTaskEvent, SupportScanState, SupportTaskPreview)
]
