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


# 整单退款申请表：保存自动/人工退款、退货物流和审核信息；当前是模拟退款。
class RefundRequest(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "refund_requests"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_refund_user_request"),
        CheckConstraint(
            "status IN ('review_pending','awaiting_return','return_in_transit','refunded','rejected','withdrawn')",
            name="ck_refund_status",
        ),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商城订单主键。 外键：shop_orders.id。
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 关联的订单客服会话主键；会话被删除时设为空，不删除退款申请。 外键：chat_sessions.id。 数据库允许 NULL。
    chat_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    # 客户端生成的幂等请求标识，用于识别网络重试、防止重复处理。
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # 请求内容的 SHA-256 指纹；检测同一 request_key 是否被用于不同内容。
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 退款原因编码：not_needed 不想要、wrong_order 拍错、change_mind 改变主意、not_received 未收到、quality 质量、damaged 破损、payment_issue 支付异常、other 其他。
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    # 用户填写的退款情况说明。
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 本次退款申请确认的联系电话，不随地址簿修改。
    contact_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    # 用户申请时声明是否已收到货，用于路由人工审核及是否需要退货。
    received: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 本次整单模拟退款金额，创建时取订单 total，Decimal 保留两位小数。
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # 三字符币种代码，例如 USD；金额应结合该字段解释。
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # 申请状态：review_pending 待审核、awaiting_return 待寄回、return_in_transit 退货途中、refunded 已退款、rejected 已拒绝、withdrawn 已撤销。
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 规则选择自动处理或人工审核的文字理由，不是用户填写的退款原因。
    route_reason: Mapped[str] = mapped_column(Text, nullable=False)
    # 创建申请时的订单状态快照；用于判断退款时是否应恢复未发货库存。
    original_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 是否已因本申请恢复库存，默认 False；避免重复完成退款时再次加库存。
    stock_restored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 执行人工审核或退货验收的客服用户主键；尚无人工审核时可为空。 外键：users.id。 数据库允许 NULL。
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # 人工审核处理意见；未审核时通常为空。 数据库允许 NULL。
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 客服批准退货后提供的完整退货地址及联系人；不需退货时可为空。 数据库允许 NULL。
    return_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 批准退货后建议寄回的截止时间，当前流程设为批准后 7 天；未要求退货时为空。 数据库允许 NULL。
    return_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 用户寄回商品所用的快递公司，不是原订单发货公司。 数据库允许 NULL。
    return_carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 用户提交的退货快递单号，不是原订单发货单号。 数据库允许 NULL。
    return_tracking: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 最近更新时间；模型仅提供初始默认值，后续更新由业务代码维护。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 本申请完成模拟退款的时间；尚未退款时为空。 数据库允许 NULL。
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


# 私有退款凭证表：记录用户上传的图片，可先上传再关联退款申请。
class RefundEvidence(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "refund_evidence"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # 关联的商城订单主键。 外键：shop_orders.id。
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False
    )
    # 绑定的退款申请主键；刚上传、尚未提交申请时为空，关联申请后不可被其他申请复用。 外键：refund_requests.id。 数据库允许 NULL。
    refund_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("refund_requests.id"), index=True, nullable=True
    )
    # 相对素材根目录的私有图片路径，位于 private_refund_evidence；需通过鉴权接口读取。
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 退款操作事件表：按时间保留提交、审核、退货及退款等处理轨迹。
class RefundEvent(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "refund_events"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的退款申请主键。 外键：refund_requests.id。
    refund_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("refund_requests.id"), nullable=False, index=True
    )
    # 执行操作的用户主键。 外键：users.id。
    actor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 退款事件动作编码，如 submitted 提交、withdrawn 撤销、return_shipped 寄回、return_authorized 批准退货、rejected 拒绝、refunded 退款。
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    # 本次退款动作说明，供审核追溯；模拟退款事件会注明无真实资金转账。
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 催发货记录表：记录客户催促和管理员处理结果，不直接触发发货。
class ShipmentReminder(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "shipment_reminders"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商城订单主键。 外键：shop_orders.id。
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 客户提交的催发货备注。
    note: Mapped[str] = mapped_column(String(500), nullable=False)
    # 催促状态：pending 待处理、handled 已处理；默认 pending。
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 客服处理说明；发货流程也会写入已发货提示，未处理时可为空。 数据库允许 NULL。
    handled_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 催发货处理完成时间；未处理时为空。 数据库允许 NULL。
    handled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


AFTERSALES_TABLES = [
    m.__table__ for m in (RefundRequest, RefundEvidence, RefundEvent, ShipmentReminder)
]
