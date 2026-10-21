"""Server-owned demo refund policy. No LLM is permitted to decide or execute money writes."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.database.aftersales_models import RefundRequest, RefundEvent, ShipmentReminder
from app.database.activity_models import ChatSession, ChatMessage

ACTIVE_REFUNDS = ("review_pending", "awaiting_return", "return_in_transit")
REASONS = {
    "not_needed": "不想要了",
    "wrong_order": "拍错商品",
    "change_mind": "改变主意",
    "not_received": "物流异常/未收到货",
    "quality": "质量问题",
    "damaged": "商品破损",
    "payment_issue": "支付异常",
    "other": "其他原因",
}


def now():
    return datetime.now(timezone.utc)


def refund_policy():
    return {
        "demo": True,
        "version": "demo-v1",
        "scope": "整单全额模拟退款，不发生真实资金转账",
        "auto_rule": "已支付未发货，支付后24小时内，未收到货，原因是不想要、拍错或改变主意：自动全额模拟退款。",
        "manual_rule": "已发货、已收货、支付超过24小时，或质量/破损/支付异常/其他情况：人工审核。",
        "return_rule": "已收到货的已发货/已完成订单：人工批准后提供退货地址，用户填写退货快递单号，客服验收后退款。未收到货的物流争议由客服核实后处理。",
        "timing": "已收货7天内优先按常规售后处理，超过7天仍可提交人工评估；这不是自动拒绝条件。退货批准后建议7天内寄出。",
        "required": ["退款原因", "至少10字情况说明", "确认联系电话", "是否收到货"],
        "evidence_rule": "质量或破损必须上传至少1张、最多3张照片；其他原因照片可选。每张最多5MB。无需银行卡、验证码或账户密码。",
        "reasons": [
            {
                "code": code,
                "label": label,
                "requires_evidence": code in ("quality", "damaged"),
            }
            for code, label in REASONS.items()
        ],
    }


def auto_route(order, reason, received):
    return (
        order.status == "paid"
        and order.paid_at is not None
        and timedelta(0) <= now() - order.paid_at <= timedelta(hours=24)
        and reason in ("not_needed", "wrong_order", "change_mind")
        and not received
    )


def active_refund(db, order_id):
    return db.scalar(
        select(RefundRequest)
        .where(
            RefundRequest.order_id == order_id, RefundRequest.status.in_(ACTIVE_REFUNDS)
        )
        .limit(1)
    )


def latest_summary(db, order_id):
    refund = db.scalar(
        select(RefundRequest)
        .where(RefundRequest.order_id == order_id)
        .order_by(RefundRequest.id.desc())
        .limit(1)
    )
    reminder = db.scalar(
        select(ShipmentReminder)
        .where(ShipmentReminder.order_id == order_id)
        .order_by(ShipmentReminder.id.desc())
        .limit(1)
    )
    return {
        "refund": (
            {
                "id": refund.id,
                "status": refund.status,
                "amount": str(refund.amount),
                "currency": refund.currency,
                "route_reason": refund.route_reason,
                "chat_session_id": refund.chat_session_id,
            }
            if refund
            else None
        ),
        "reminder": (
            {
                "id": reminder.id,
                "status": reminder.status,
                "created_at": reminder.created_at,
                "handled_note": reminder.handled_note,
                "note": reminder.note,
            }
            if reminder
            else None
        ),
    }


def order_session(db, order, intent="general", human=False):
    # Call only while holding this order's row lock, so concurrent entries reuse a session.
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


def event(db, refund, user_id, action, note):
    db.add(RefundEvent(refund_id=refund.id, actor_id=user_id, action=action, note=note))
    refund.updated_at = now()


def complete_refund(db, order, refund, user_id, note):
    if refund.status == "refunded":
        return
    if order.status == "refunded":
        raise ValueError("Order already refunded")
    if refund.original_status == "paid" and not refund.stock_restored:
        from app.api.shop import release_stock

        release_stock(db, [order])
        refund.stock_restored = True
    # Returned or lost shipped goods are not automatically made saleable again.
    order.status = "refunded"
    order.refunded_at = now()
    refund.status = "refunded"
    refund.refunded_at = now()
    event(db, refund, user_id, "refunded", note + "（模拟退款，无真实扣款或转账）")
