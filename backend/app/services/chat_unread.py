"""Per-viewer read watermarks; loading a conversation never implicitly marks it read."""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import and_, or_, func, select
from sqlalchemy.dialects.postgresql import insert
from app.database.activity_models import ChatMessage, ChatSession, ChatReadState


def unread_query(user, admin=False, session_ids=None):
    """构造当前查看者每个会话的未读消息计数查询。

    输入：
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        admin: bool，是否采用客服未读规则，默认 False（客户规则）。
        session_ids: 会话主键集合或 None；None 不额外限制，空集合不匹配任何会话。

    输出：
        SQLAlchemy Select：每行包含 session_id、unread_count；不执行查询。

    流程：
        1. 按 admin 决定接收消息角色
        2. 排除 pending
        3. 用消息 updated_at 对比个人已读水位
        4. 客户侧限制会话归属
        5. 可选筛选会话集合
        6. 按会话分组。
    """
    # 未读按“查看者 + 会话”独立计算：客户关注 AI/客服消息，管理员关注客户及其他客服消息。
    # 用 updated_at 比较水位，因此原先 pending 的回复生成完成后仍能被识别为新消息。
    incoming = (
        or_(
            ChatMessage.role == "user",
            and_(
                ChatMessage.role == "human_agent",
                ChatMessage.staff_user_id.is_distinct_from(user.id),
            ),
        )
        if admin
        else ChatMessage.role.in_(["assistant", "human_agent"])
    )
    query = (
        select(ChatMessage.session_id, func.count().label("unread_count"))
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .outerjoin(
            ChatReadState,
            and_(
                ChatReadState.session_id == ChatMessage.session_id,
                ChatReadState.user_id == user.id,
            ),
        )
        .where(
            incoming,
            ChatMessage.status != "pending",
            or_(
                ChatReadState.last_read_at.is_(None),
                ChatMessage.updated_at > ChatReadState.last_read_at,
            ),
        )
    )
    if not admin:
        query = query.where(ChatSession.user_id == user.id)
    if session_ids is not None:
        query = query.where(ChatMessage.session_id.in_(session_ids))
    return query.group_by(ChatMessage.session_id)


def unread_counts(db, user, admin=False, session_ids=None):
    """执行未读查询并转换成会话到数量的映射。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        admin: bool，是否采用客服未读规则，默认 False（客户规则）。
        session_ids: 会话主键集合或 None；None 不额外限制，空集合不匹配任何会话。

    输出：
        dict[int, int]：{session_id: unread_count}，无未读的会话可能不在字典中。

    流程：
        1. 调用 unread_query 构建条件
        2. 执行查询
        3. 将结果行转为字典；不提交。
    """
    return dict(db.execute(unread_query(user, admin, session_ids)).all())


def read_through(entries):
    """计算这一批消息可以确认到的已读时间水位。

    输入：
        entries: ChatMessage 对象序列。

    输出：
        datetime 或 None：非 pending 消息最大的 updated_at；没有符合消息时为 None。

    流程：
        1. 过滤 pending
        2. 取最大更新时间；只处理内存数据，不访问数据库。
    """
    return max((m.updated_at for m in entries if m.status != "pending"), default=None)


def mark_read(db, user, session_id, body):
    """显式推进某查看者在会话中的已读进度。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        session_id: int，会话主键。
        body: ReadThrough：read_through，前端明确确认的已读截止时间。

    输出：
        dict：status=read。

    流程：
        1. 拒绝未来时间（422）→ 按会话和用户插入或更新 ChatReadState
        2. 使用 greatest 保证水位不倒退
        3. 提交；会话访问权限须由调用方先验证。
    """
    # 前端显式确认已读，GET 会话本身不清零；取较大时间，避免乱序请求把已读进度倒退。
    if body.read_through > datetime.now(timezone.utc):
        raise HTTPException(422, "已读时间不能晚于当前时间")
    statement = insert(ChatReadState).values(
        session_id=session_id, user_id=user.id, last_read_at=body.read_through
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["session_id", "user_id"],
            set_={
                "last_read_at": func.greatest(
                    ChatReadState.last_read_at, statement.excluded.last_read_at
                )
            },
        )
    )
    db.commit()
    return {"status": "read"}
