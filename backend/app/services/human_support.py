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
    """为客服后台读取会话并按需加锁。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        session_id: int，会话主键。
        lock: bool，是否对查询结果加行锁，默认 False。

    输出：
        ChatSession ORM 对象；不存在时抛 404。

    流程：
        1. 按 session_id 查询
        2. lock=True 时 FOR UPDATE
        3. 返回会话；不提交，不限制客户归属，客服权限由路由验证。
    """
    query = select(ChatSession).where(ChatSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        raise HTTPException(404, "会话不存在")
    return session


def staff_message_data(message, user):
    """为客服展示消息并标记是否是自己发送的人工回复。

    输入：
        message: ChatMessage ORM 对象。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：message_data 字段加 is_mine 布尔值。

    流程：
        1. 序列化消息
        2. 比较角色 human_agent 及 staff_user_id 与 user.id
        3. 合并标记；不提交。
    """
    return {
        **message_data(message),
        "is_mine": message.role == "human_agent" and message.staff_user_id == user.id,
    }


def handoff(session_id, db, user):
    """让客户将本人订单会话转交人工。

    输入：
        session_id: int，会话主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：更新后的会话摘要。

    流程：
        1. 校验归属并锁会话
        2. 要求已绑定订单（否则 409）→ 调用 handoff_session
        3. flush、组装、提交。
    """
    session = owned_session(db, user, session_id, lock=True)
    if session.order_id is None:
        raise HTTPException(409, "请从需要咨询的订单进入人工客服")
    handoff_session(db, session)
    db.flush()
    result = session_data(session)
    db.commit()
    return result


def inbox(status, page, unread_only, db, user):
    """分页提供客服收件箱，优先显示有未读消息的会话。

    输入：
        status: str，状态筛选条件，具体允许值由路由约束。
        page: int，从 1 开始的页码（由路由校验）。
        unread_only: bool，是否仅展示有未读消息的会话。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：items（含 customer_name、unread_count）、total、total_pages。

    流程：
        1. 构建管理员未读子查询
        2. 按人工状态/仅未读过滤
        3. 统计并在分页前按未读与时间排序
        4. 每页 20 条
        5. 批量补充客户名及计数；不提交。
    """
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
    """汇总当前客服视角下的未读消息。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：total、sessions 会话到未读数的映射。

    流程：
        1. 调用 unread_counts(admin=True)
        2. 累加各会话计数；不提交。
    """
    counts = unread_counts(db, user, admin=True)
    return {"total": sum(counts.values()), "sessions": counts}


def read_session(session_id, body, db, user):
    """确认客服已读某会话中的消息。

    输入：
        session_id: int，会话主键。
        body: ReadThrough：read_through 已读截止时间。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：status=read。

    流程：
        1. staff_session 确认会话存在
        2. mark_read 保存此客服的个人已读水位并提交；客服权限由路由校验。
    """
    staff_session(db, session_id)
    return mark_read(db, user, session_id, body)


def detail(session_id, before_id, db, user):
    """读取客服会话详情、历史消息和关联跟进待办。

    输入：
        session_id: int，会话主键。
        before_id: 消息主键游标或 None；有值时仅返回更早的消息。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：session、items、has_more、read_through、support_tasks、assist_version。

    流程：
        1. 查会话
        2. 按 before_id 游标倒序取 51 条消息
        3. 查询订单活动待办
        4. 将前 50 条反转并标记 is_mine
        5. 计算助手快照版本；不提交、不自动标记已读。
    """
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
    """根据会话快照生成供客服参考的 AI 接待建议。

    输入：
        session_id: int，会话主键。
        body: AssistantRequest 或 None；当前实现未读取此参数，保留接口兼容。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        staff_assistant.invoke 的结果（助手建议）；模型配置或调用失败抛 503。

    流程：
        1. 读取会话、最近消息及待办
        2. 使用会话所属客户身份构造有长度上限的上下文和版本
        3. rollback 释放读取事务
        4. 调用助手；不发送客户消息、不接管会话。
    """
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
    """发送可幂等重试的人工客服回复并接管会话。

    输入：
        session_id: int，会话主键。
        body: Reply：content 回复内容、request_key 幂等请求标识。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：人工消息字段及 is_mine。

    流程：
        1. 锁会话
        2. 按 request_key 查重并校验内容
        3. 拒绝已关闭会话
        4. 结束 AI 占位
        5. 新增 human_agent 消息
        6. 会话改 active 并记录客服
        7. flush、组装、提交。
    """
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
    """结束本次人工接待。

    输入：
        session_id: int，会话主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：status=closed。

    流程：
        1. 锁会话
        2. 写 human_status=closed、操作者和更新时间
        3. 提交；后续客户消息可再进入 AI 流程。
    """
    # 结束本次人工接待；客户后续继续提问时可以重新进入 AI 流程。
    session = staff_session(db, session_id, lock=True)
    session.human_status = "closed"
    session.staff_user_id = user.id
    session.updated_at = now()
    db.commit()
    return {"status": "closed"}
