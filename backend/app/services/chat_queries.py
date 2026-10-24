"""聊天归属校验、消息序列化与中断回复恢复。

公共查询和数据组装供业务用例复用，本模块不提交事务。
"""

from app.services.clock import now

import logging
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.database.activity_models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


def owned_session(db, user, session_id, lock=False):
    """查询属于当前用户的会话，必要时加行锁。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        session_id: int，会话主键。
        lock: bool，是否对查询结果加行锁，默认 False。

    输出：
        ChatSession ORM 对象；不存在或不属于用户时返回 404。

    流程：
        1. 按 session_id 和 user.id 筛选
        2. lock=True 时使用 FOR UPDATE
        3. 执行查询；不提交。
    """
    # 会话归属校验集中在这里；需要修改时同时加行锁，避免同一会话并发写入互相覆盖。
    query = select(ChatSession).where(
        ChatSession.id == session_id, ChatSession.user_id == user.id
    )
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        raise HTTPException(404, "会话不存在")
    return session


def session_data(session):
    """把会话对象转换为接口可用的摘要。

    输入：
        session: ChatSession ORM 对象。

    输出：
        dict：会话 id、标题、关联商品/订单、上下文、时间、意图及人工状态。

    流程：
        1. 读取指定 ORM 属性
        2. 组装字典；不执行额外查询、不提交。
    """
    return {
        key: getattr(session, key)
        for key in (
            "id",
            "title",
            "product_id",
            "order_id",
            "context_name",
            "created_at",
            "updated_at",
            "intent",
            "human_status",
        )
    }


def message_data(message):
    """把消息对象转换为接口响应字段。

    输入：
        message: ChatMessage ORM 对象。

    输出：
        dict：id、role、content、status、request_key、created_at、agent_metadata。

    流程：
        1. 提取消息公开字段
        2. 返回字典；不修改消息、不提交。
    """
    return {
        key: getattr(message, key)
        for key in (
            "id",
            "role",
            "content",
            "status",
            "request_key",
            "created_at",
            "agent_metadata",
        )
    }


def recover_interrupted(db, session_id):
    """恢复长时间未完成的 AI 回复占位，允许用户重试。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        session_id: int，会话主键。

    输出：
        None；将超时 pending 消息改成 failed 并设置提示。

    流程：
        1. 查询指定会话中超过 2 分钟未更新的 pending 消息
        2. 更新状态、内容和时间
        3. flush；不 commit，由调用方提交。
    """
    # 读取或发送时恢复长时间停留在 pending 的消息，允许用户重试中断的生成。
    entries = db.scalars(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.status == "pending",
            ChatMessage.updated_at < now() - timedelta(minutes=2),
        )
    ).all()
    for entry in entries:
        entry.status = "failed"
        entry.content = "回复中断，可点击重试。"
        entry.updated_at = now()
    db.flush()
