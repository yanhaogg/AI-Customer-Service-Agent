"""人工会话列表、接管、回复、结束及助手建议快照。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database.models import User
from app.database.activity_models import ChatSession, ChatMessage
from app.services.chat_queries import owned_session, session_data, message_data
from app.services.clock import now
from app.services.conversations import handoff_session
from app.services.chat_unread import (
    unread_counts,
    unread_query,
    read_through,
    mark_read,
)
from app.agent.staff_assistant import staff_assistant, snapshot_version
from app.agent.config import AgentConfigurationError, AgentUnavailableError
from app.services.support_tasks import order_tasks


def staff_session(db, session_id, lock=False):
    query = select(ChatSession).where(ChatSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        raise HTTPException(404, "会话不存在")
    return session


def staff_message_data(message, user):
    return {
        **message_data(message),
        "is_mine": message.role == "human_agent" and message.staff_user_id == user.id,
    }


def handoff(session_id, db, user):
    session = owned_session(db, user, session_id, lock=True)
    if session.order_id is None:
        raise HTTPException(409, "请从需要咨询的订单进入人工客服")
    handoff_session(db, session)
    db.flush()
    result = session_data(session)
    db.commit()
    return result


def inbox(status, page, unread_only, db, user):
    # 管理员查看客户与 AI/人工的会话；未读优先排序在数据库分页前完成。
    unread = unread_query(user, admin=True).subquery()
    count = func.coalesce(unread.c.unread_count, 0)
    query = select(ChatSession).outerjoin(unread, unread.c.session_id == ChatSession.id)
    if status != "all":
        query = query.where(ChatSession.human_status == status)
    if unread_only:
        query = query.where(count > 0)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    entries = db.scalars(
        query.order_by(
            (count > 0).desc(), ChatSession.updated_at.desc(), ChatSession.id.desc()
        )
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    counts = unread_counts(db, user, admin=True, session_ids=[s.id for s in entries])
    owners = dict(
        db.execute(
            select(User.id, User.username).where(
                User.id.in_([s.user_id for s in entries])
            )
        ).all()
    )
    return {
        "items": [
            {
                **session_data(s),
                "customer_name": owners.get(s.user_id),
                "unread_count": counts.get(s.id, 0),
            }
            for s in entries
        ],
        "total": total,
        "total_pages": (total + 19) // 20,
    }


def unread(db, user):
    counts = unread_counts(db, user, admin=True)
    return {"total": sum(counts.values()), "sessions": counts}


def read_session(session_id, body, db, user):
    staff_session(db, session_id)
    return mark_read(db, user, session_id, body)


def detail(session_id, before_id, db, user):
    session = staff_session(db, session_id)
    query = select(ChatMessage).where(ChatMessage.session_id == session_id)
    if before_id:
        query = query.where(ChatMessage.id < before_id)
    entries = db.scalars(query.order_by(ChatMessage.id.desc()).limit(51)).all()
    tasks = order_tasks(db, session.order_id)
    return {
        "session": session_data(session),
        "items": [staff_message_data(m, user) for m in reversed(entries[:50])],
        "has_more": len(entries) > 50,
        "read_through": read_through(entries[:50]),
        "support_tasks": tasks,
        "assist_version": snapshot_version(session, entries[:50], tasks),
    }


def assistant(session_id, body, db, user):
    # 读取有限聊天快照和待办上下文，释放事务后生成接待建议；此接口不发送回复或接管会话。
    session = staff_session(db, session_id)
    entries = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(51)
    ).all()
    # Identity is the customer who owns the inspected thread, never the administrator or client input.
    tasks = order_tasks(db, session.order_id)
    payload = {
        "user_id": session.user_id,
        "order_id": session.order_id,
        "product_id": session.product_id,
        "support_tasks": tasks,
        "title": session.title,
        "human_status": session.human_status,
        "snapshot_version": snapshot_version(session, entries[:50], tasks),
        "has_older_messages": len(entries) > 50,
        "messages": [],
    }
    remaining = 24000
    for message in entries[:50]:
        content = message.content[: min(3000, remaining)]
        if not content:
            if message.status != "pending":
                payload["has_older_messages"] = True
            continue
        payload["messages"].append(
            {"role": message.role, "content": content, "status": message.status}
        )
        remaining -= len(content)
        if len(content) < len(message.content):
            payload["has_older_messages"] = True
    payload["messages"].reverse()
    bind = db.get_bind()
    payload["session_factory"] = lambda: Session(bind=bind)
    # Release the snapshot transaction before waiting on the model; never mark read, take over or send.
    db.rollback()
    try:
        return staff_assistant.invoke(payload)
    except AgentConfigurationError:
        raise HTTPException(
            503, "客服助手模型尚未配置，请管理员检查模型配置。"
        ) from None
    except AgentUnavailableError as error:
        raise HTTPException(503, str(error)) from None
    except Exception:
        raise HTTPException(503, "客服助手暂时不可用，请稍后重试。") from None


def reply(session_id, body, db, user):
    # 人工消息与请求编号一起保存以防重复发送；发出回复时接管会话，暂停后续 AI 自动回复。
    session = staff_session(db, session_id, lock=True)
    previous = db.scalar(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.request_key == body.request_key,
            ChatMessage.role == "human_agent",
        )
    )
    if previous:
        if previous.content != body.content:
            raise HTTPException(409, "请求编号已用于其他回复")
        result = staff_message_data(previous, user)
        db.commit()
        return result
    if session.human_status == "closed":
        raise HTTPException(409, "该人工会话已结束")
    handoff_session(db, session)
    message = ChatMessage(
        session_id=session_id,
        role="human_agent",
        staff_user_id=user.id,
        content=body.content,
        request_key=body.request_key,
        status="completed",
        agent_metadata={"mode": "human_support"},
    )
    db.add(message)
    session.human_status = "active"
    session.staff_user_id = user.id
    session.updated_at = now()
    db.flush()
    result = staff_message_data(message, user)
    db.commit()
    return result


def close(session_id, db, user):
    # 结束本次人工接待；客户后续继续提问时可以重新进入 AI 流程。
    session = staff_session(db, session_id, lock=True)
    session.human_status = "closed"
    session.staff_user_id = user.id
    session.updated_at = now()
    db.commit()
    return {"status": "closed"}
