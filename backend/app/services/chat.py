"""客户会话与消息用例；生成前提交，释放事务后调用多 Agent，再检查版本回写。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

import logging
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database.catalog_models import Product
from app.database.shop_models import ShopOrder
from app.database.activity_models import ChatMessage, ChatSession
from app.storage import VISIBLE_STATUSES
from app.agent.graph import support_agent
from app.agent.config import (
    load_settings,
    AgentConfigurationError,
    AgentUnavailableError,
)
from app.services.chat_unread import unread_counts, read_through, mark_read
from app.services.chat_queries import (
    owned_session,
    session_data,
    message_data,
    recover_interrupted,
)
from app.services.clock import now
from app.services.user_access import lock_user

logger = logging.getLogger(__name__)


def agent_status():
    try:
        settings = load_settings()
        return {
            "configured": True,
            "model": settings.model,
            "mode": "manager_multi_agent",
            "agents": ["product_agent", "order_agent", "aftersales_agent"],
        }
    except AgentConfigurationError as error:
        return {
            "configured": False,
            "model": None,
            "mode": "manager_multi_agent",
            "message": str(error),
        }


def create_session(body, db, user):
    # 普通咨询可新建会话；绑定订单时复用该订单已有会话，避免催发货与售后各开一条。
    lock_user(db, user)
    context = []
    order_id = None
    if body.product_id:
        product = db.scalar(
            select(Product).where(
                Product.id == body.product_id, Product.status.in_(VISIBLE_STATUSES)
            )
        )
        if product is None:
            raise HTTPException(404, "商品不存在或已删除")
        context.append(product.name_zh or product.name_original)
    if body.order_number:
        order = db.scalar(
            select(ShopOrder)
            .where(ShopOrder.number == body.order_number, ShopOrder.user_id == user.id)
            .with_for_update()
        )
        if order is None:
            raise HTTPException(404, "订单不存在")
        from app.services.conversations import order_session

        existing = db.scalar(
            select(ChatSession.id).where(ChatSession.order_id == order.id)
        )
        if (
            existing is None
            and db.scalar(
                select(func.count())
                .select_from(ChatSession)
                .where(ChatSession.user_id == user.id)
            )
            >= 500
        ):
            raise HTTPException(422, "最多保存 500 个会话，请先删除不需要的记录")
        session = order_session(db, order)
        if session.product_id is None and body.product_id:
            session.product_id = body.product_id
        db.flush()
        result = session_data(session)
        db.commit()
        return result
    if (
        db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == user.id)
        )
        >= 500
    ):
        raise HTTPException(422, "最多保存 500 个会话，请先删除不需要的记录")
    session = ChatSession(
        user_id=user.id,
        title=body.title,
        product_id=body.product_id,
        order_id=order_id,
        context_name=" / ".join(context) or None,
    )
    db.add(session)
    db.flush()
    result = session_data(session)
    db.commit()
    return result


def sessions(page, q, db, user):
    query = select(ChatSession).where(ChatSession.user_id == user.id)
    if q.strip():
        query = query.where(ChatSession.title.icontains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    counts = unread_counts(db, user, session_ids=[s.id for s in rows])
    return {
        "items": [
            {**session_data(s), "unread_count": counts.get(s.id, 0)} for s in rows
        ],
        "total": total,
        "total_pages": (total + 19) // 20,
    }


def unread(db, user):
    counts = unread_counts(db, user)
    return {"total": sum(counts.values()), "sessions": counts}


def read_session(session_id, body, db, user):
    owned_session(db, user, session_id)
    return mark_read(db, user, session_id, body)


def messages(session_id, before_id, db, user):
    session = owned_session(db, user, session_id, lock=True)
    recover_interrupted(db, session_id)
    query = select(ChatMessage).where(ChatMessage.session_id == session_id)
    if before_id:
        query = query.where(ChatMessage.id < before_id)
    entries = db.scalars(query.order_by(ChatMessage.id.desc()).limit(51)).all()
    result = {
        "session": session_data(session),
        "items": [message_data(m) for m in reversed(entries[:50])],
        "has_more": len(entries) > 50,
        "read_through": read_through(entries[:50]),
    }
    db.commit()
    return result


def delete_session(session_id, db, user):
    session = owned_session(db, user, session_id, lock=True)
    db.delete(session)
    db.commit()


def send_message(session_id, body, db, user):
    # 聊天主流程：校验归属与重复请求 → 保存用户消息和回复占位 → 调用多 Agent → 回写结果。
    # 人工接待中的消息只落库并确认送达，不再调用模型自动回复。
    session = owned_session(db, user, session_id, lock=True)
    recover_interrupted(db, session_id)
    existing = db.scalars(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.request_key == body.request_key,
        )
    ).all()
    previous = {m.role: m for m in existing}
    if existing:
        if previous["user"].content != body.content:
            raise HTTPException(409, "该请求编号已用于另一条消息")
        assistant = previous["assistant"]
        if assistant.status != "failed":
            status_code = 202 if assistant.status == "pending" else 200
            result = {
                "items": [message_data(previous["user"]), message_data(assistant)]
            }
            db.commit()
            return result, status_code
    if db.scalar(
        select(ChatMessage.id)
        .where(ChatMessage.session_id == session_id, ChatMessage.status == "pending")
        .limit(1)
    ):
        raise HTTPException(409, "上一条消息正在回复，请稍候")
    if not existing:
        if (
            db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.session_id == session_id)
            )
            >= 2000
        ):
            raise HTTPException(422, "当前会话消息较多，请新建会话继续咨询")
        user_message = ChatMessage(
            session_id=session_id,
            request_key=body.request_key,
            role="user",
            content=body.content,
            status="completed",
        )
        assistant = ChatMessage(
            session_id=session_id,
            request_key=body.request_key,
            role="assistant",
            content="",
            status="pending",
        )
        db.add_all([user_message, assistant])
        db.flush()
        previous["user"] = user_message
    else:
        assistant.status = "pending"
        assistant.content = ""
        assistant.updated_at = now()
    session.updated_at = now()
    generation_started = now()
    assistant.updated_at = generation_started
    if session.human_status in ("waiting", "active"):
        assistant.status = "completed"
        assistant.content = "消息已送达人工客服，请等待客服回复。"
        assistant.agent_metadata = {"mode": "human_handoff"}
        db.flush()
        result = {"items": [message_data(previous["user"]), message_data(assistant)]}
        db.commit()
        return result, 200
    assistant_id = assistant.id
    order = db.get(ShopOrder, session.order_id) if session.order_id else None
    order_number = order.number if order else ""
    product_id = session.product_id
    verified_user_id = user.id
    current_message_id = previous["user"].id
    database_bind = db.get_bind()
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(
            db.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.status == "completed",
                    ChatMessage.id <= current_message_id,
                )
                .order_by(ChatMessage.id.desc())
                .limit(20)
            ).all()
        )
    ]
    # 网络模型调用可能较慢：先提交消息并释放数据库锁，避免生成期间阻塞其他请求。
    # Persist the user message before invoking any agent. No DB locks during generation.
    db.commit()
    try:
        result = support_agent.invoke(
            {
                "user_input": body.content,
                "user_id": verified_user_id,
                "order_id": order_number,
                "product_id": product_id,
                "current_message_id": current_message_id,
                "session_factory": lambda: Session(bind=database_bind),
                "conversation_history": history,
            }
        )
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty assistant response")
        status = "completed"
        metadata = result.get("agent_metadata", {})
    except (AgentConfigurationError, AgentUnavailableError) as error:
        answer = str(error)
        status = "failed"
        metadata = {}
    except Exception:
        logger.warning("Chat generation failed for message %s", assistant_id)
        answer = "客服模型暂时无法回复，你的消息已保存，请稍后重试。"
        status = "failed"
        metadata = {}
    session = owned_session(db, user, session_id, lock=True)
    # 用 pending 状态与本次生成时间作双重校验，防止超时重试或人工接管后被旧答案覆盖。
    # A timeout recovery/retry must never be overwritten by a late original response.
    assistant = db.scalar(
        select(ChatMessage)
        .where(ChatMessage.id == assistant_id)
        .execution_options(populate_existing=True)
    )
    if assistant.status == "pending" and assistant.updated_at == generation_started:
        assistant.content = answer
        assistant.status = status
        assistant.updated_at = now()
        session.updated_at = now()
        assistant.agent_metadata = metadata
    db.flush()
    result = {"items": [message_data(previous["user"]), message_data(assistant)]}
    db.commit()
    return result, 200
