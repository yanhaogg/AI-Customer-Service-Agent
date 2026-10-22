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
