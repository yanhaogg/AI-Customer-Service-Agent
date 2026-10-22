"""订单会话复用与人工接管；调用方持有订单锁，由所属业务用例提交事务。"""

from sqlalchemy import select
from app.database.activity_models import ChatSession, ChatMessage
from .clock import now


def order_session(db, order, intent="general", human=False):
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
