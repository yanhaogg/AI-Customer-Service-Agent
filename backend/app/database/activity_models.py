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


# 客户会话表：可关联商品或订单；同一非空订单主键只对应一个会话。
class ChatSession(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "chat_sessions"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (UniqueConstraint("order_id", name="uq_chat_order"),)
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 会话标题，用于列表展示和关键词搜索。
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    # 可选的咨询商品主键；纯订单或普通咨询可为空。 外键：products.id。 数据库允许 NULL。
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=True
    )
    # 可选的商城订单主键；非空时受唯一约束，同一订单复用一个会话。 外键：shop_orders.id。 数据库允许 NULL。
    order_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=True
    )
    # 上下文展示名称，如商品名或订单号；没有关联上下文时可为空。 数据库允许 NULL。
    context_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 咨询意图，默认 general；当前订单会话统一复用，新建时不再按意图区分会话。
    intent: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general", server_default="general"
    )
    # 人工接待状态：none 未转人工、waiting 等待接待、active 接待中、closed 本次接待已结束。
    human_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    # 当前接待或最近结束接待的客服主键；等待重新接待时可清空。 外键：users.id。 数据库允许 NULL。
    staff_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 会话最近活动时间，发消息/转人工等流程维护，用于会话列表排序。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index(
    "ix_chat_user_recent",
    ChatSession.user_id,
    ChatSession.updated_at.desc(),
    ChatSession.id.desc(),
)


# 聊天消息表：保存客户、AI 和人工客服消息，包含生成状态和请求去重信息。
class ChatMessage(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "chat_messages"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
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
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属聊天会话主键。 外键：chat_sessions.id。
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # 本次发消息请求标识；与 session_id、role 联合唯一，同一请求可同时有 user 与 assistant 两条消息。
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # 发送方角色：user 客户、assistant AI、human_agent 人工客服。
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # 消息正文；AI 生成占位消息的正文可暂为空字符串。
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Agent 执行信息 JSON，如处理模式/路由等；默认空对象，不作为用户身份或权限依据。
    agent_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # 人工消息的发送客服主键；客户或 AI 消息一般为空，用于识别是谁回复的。 外键：users.id。 数据库允许 NULL。
    staff_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # 消息状态：pending 生成中、completed 完成、failed 失败；失败的 AI 回复可重试。
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 消息最近状态/内容更新时间；用于超时恢复、未读水位比较及防止迟到回复覆盖新结果。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 商品浏览历史表：同用户同商品合并为一条，记录访问次数及展示快照。
class BrowsingHistory(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "product_browsing_history"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_browsing_user_product"),
        CheckConstraint("view_count > 0", name="ck_browsing_count"),
        Index("ix_browsing_user_recent", "user_id", "last_viewed_at"),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 关联的商品主键。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    # 记录浏览时的商品名称快照，便于商品不可用时仍展示历史信息。
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    # 浏览记录保存的商品图片快照主键；无图时为空。 外键：media_assets.id。 数据库允许 NULL。
    image_asset_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media_assets.id"), nullable=True
    )
    # 首次创建这条商品浏览记录的时间。
    first_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 最近一次有效浏览时间，用于排序和只保留最近 500 款商品。
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 累计有效浏览次数，初始为 1、必须大于 0；同一 visit_key 重试不累加。
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 最近一次访问的去重标识，用于区分新浏览和同一次请求重试。
    last_visit_key: Mapped[str] = mapped_column(String(64), nullable=False)


# 个人已读进度表：以会话和查看者为联合主键，客户及不同客服分别记录进度。
class ChatReadState(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "chat_read_states"
    # 被阅读的会话主键，与 user_id 一起构成联合主键；删除会话时级联删除。 外键：chat_sessions.id。
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    # 查看者的用户主键，可为客户或客服；各查看者独立维护已读进度，删除用户时级联删除。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    # 已读截止时间水位；消息 updated_at 晚于此值时可计为未读，更新时只前进不倒退。
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


ACTIVITY_TABLES = [
    model.__table__
    for model in (ChatSession, ChatMessage, BrowsingHistory, ChatReadState)
]
