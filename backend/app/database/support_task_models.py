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


# 内部订单跟进待办表：保存确定性规则命中的事项、负责人、事实快照和 AI 建议。
class SupportTask(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "support_tasks"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
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
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商城订单主键。 外键：shop_orders.id。
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    # 规则类型：shipping_overdue 未及时发货、receipt_overdue 久未确认收货、refund_overdue 退款审核超时。
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # 规则事实来源标识，如 paid、shipped 或 refund:<退款主键>，用于区分及去重。
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    # 供界面展示的标题。
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    # 待办状态：pending 待认领、in_progress 跟进中、resolved 已解决、dismissed 已忽略。
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 优先级，当前规则使用 high 高优先级或 normal 普通，用于列表排序。
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    # 认领待办的客服用户主键；未认领或已释放时为空。 外键：users.id。 数据库允许 NULL。
    assignee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # 规则超时阈值到达时间，如 paid_at 加 48 小时；不是客服自定的完成期限。
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 分析时的订单事实 JSON 快照，包含订单/退款状态、时间和规则信息。
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    # 事实快照的 SHA-256 指纹，用于判断分析期间事实是否变化。
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # AI 生成的内部跟进建议 JSON，仅供人工参考，不会自动执行订单操作。
    advice: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # 生成当前建议所依据的快照指纹；与 snapshot_version 不一致时不展示该建议。 数据库允许 NULL。
    advice_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # AI 分析状态：pending 待分析、generating 生成中、ready 可用、failed 失败；独立于待办业务状态。
    analysis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    # 本次分析请求的随机标识；用于阻止旧调用结果覆盖后续分析/操作结果，结束后清空。 数据库允许 NULL。
    analysis_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 最近一次分析开始时间，用于判断是否仍在生成及并发超时窗口；未分析可为空。 数据库允许 NULL。
    analysis_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 最近更新时间；模型仅提供初始默认值，后续更新由业务代码维护。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 最近记录到规则事实的时间；当前人工创建待办时初始化，不代表存在后台周期扫描。
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 人工完成或忽略待办的时间；仍在处理时为空。 数据库允许 NULL。
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 人工完成或忽略的处理说明；未关闭时通常为空。 数据库允许 NULL。
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


# 跟进待办事件表：保留认领、备注、完成和分析等操作记录。
class SupportTaskEvent(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "support_task_events"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属待办主键；待办被删除时此事件级联删除。 外键：support_tasks.id。
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 操作用户主键；无指定操作者的系统事件允许为空。 外键：users.id。 数据库允许 NULL。
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # 事件动作，如 created、claimed、released、note、resolve、dismiss、analyzed、analysis_failed。
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # 操作说明或分析结果提示，供内部审计追溯。
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 扫描状态记录表：保存扫描时间和结果；当前人工触发的待办服务未使用此模型。
class SupportScanState(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "support_scan_state"
    # 扫描状态记录主键；当前模型没有限制固定取值，也未在现行人工待办流程中读写。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    # 该状态记录对应的扫描时间，由调用方提供，模型不设置自动默认值。
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 扫描结果 JSON，具体结构取决于写入方；当前人工待办服务没有定义其使用结构。
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


# 待办分析预览表：短期保存人工确认前的分析结果，尚不是正式待办。
class SupportTaskPreview(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "support_task_previews"
    # 预览随机标识（UUID 十六进制字符串），供用户确认创建时作为 preview_id 提交。
    id: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)
    # 触发本次预览的管理员用户主键；确认创建时要求与当前操作者一致。 外键：users.id。
    actor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 关联的商城订单主键。 外键：shop_orders.id。
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False
    )
    # 规则类型：shipping_overdue 未及时发货、receipt_overdue 久未确认收货、refund_overdue 退款审核超时。
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # 规则事实来源标识，如 paid、shipped 或 refund:<退款主键>，用于区分及去重。
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    # 分析时的订单事实 JSON 快照，包含订单/退款状态、时间和规则信息。
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # 事实快照的 SHA-256 指纹，用于判断分析期间事实是否变化。
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # AI 生成的内部跟进建议 JSON，仅供人工参考，不会自动执行订单操作。
    advice: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # 预览失效时间；当前预览服务设为生成后 30 分钟，过期需重新分析。
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


SUPPORT_TASK_TABLES = [
    model.__table__
    for model in (SupportTask, SupportTaskEvent, SupportScanState, SupportTaskPreview)
]
