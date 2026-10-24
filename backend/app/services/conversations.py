"""订单会话复用与人工接管；调用方持有订单锁，由所属业务用例提交事务。"""

from sqlalchemy import select
from app.database.activity_models import ChatSession, ChatMessage
from .clock import now


def order_session(db, order, intent="general", human=False):
    """获取或创建订单共用会话，并按需转人工。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order: ShopOrder ORM 对象。
        intent: str，咨询意图，默认 general；当前不会按意图拆分订单会话。
        human: bool，是否转人工，默认 False。

    输出：
        ChatSession ORM 对象。

    流程：
        1. 调用方应先持有订单行锁
        2. 查询并锁定该用户订单最早的会话
        3. 无则创建并 flush
        4. human=True 时转人工
        5. 更新时间；不提交。intent 参数目前保留兼容，新建会话固定为 general。
    """
    # Call only while holding this order's row lock, so concurrent entries reuse a session.
    # 调用方应先持有订单行锁；同一订单共用会话，咨询意图不再作为新建会话的依据。
    session = db.scalar(
        select(ChatSession)
        .where(ChatSession.user_id == order.user_id, ChatSession.order_id == order.id)
        .order_by(ChatSession.id)
        .limit(1)
        .with_for_update()
    )
    if session is None:
        session = ChatSession(
            user_id=order.user_id,
            order_id=order.id,
            intent="general",
            title=f"订单咨询 · {order.number}",
            context_name=order.number,
            human_status="waiting" if human else "none",
        )
        db.add(session)
        db.flush()
    if human:
        handoff_session(db, session)
    session.updated_at = now()
    return session


def handoff_session(db, session):
    """将会话交给人工，并终止尚在生成的 AI 占位回复。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        session: ChatSession ORM 对象。

    输出：
        None；原地修改会话和 pending 消息。

    流程：
        1. none/closed 会话改 waiting 并清空接待人
        2. 将 pending 消息改 completed、写转人工提示和元数据
        3. 更新时间；不提交，由上层事务保存。
    """
    # 转人工时结束尚在生成的回复占位；晚到的 AI 结果不能覆盖人工接管提示。
    if session.human_status in ("none", "closed"):
        session.human_status = "waiting"
        session.staff_user_id = None
    for message in db.scalars(
        select(ChatMessage).where(
            ChatMessage.session_id == session.id, ChatMessage.status == "pending"
        )
    ):
        message.status = "completed"
        message.content = "已转人工客服，后续由人工跟进。"
        message.updated_at = now()
        message.agent_metadata = {"mode": "human_handoff"}
    session.updated_at = now()
