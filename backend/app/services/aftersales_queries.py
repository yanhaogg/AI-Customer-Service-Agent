"""售后读取与响应数据组装，不提交事务、不修改业务状态。"""

from sqlalchemy import select
from app.database.aftersales_models import (
    RefundRequest,
    RefundEvent,
    RefundEvidence,
    ShipmentReminder,
)
from app.database.activity_models import ChatSession
from .refund_policy import ACTIVE_REFUNDS


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


def refund_data(db, refund):
    result = {
        key: getattr(refund, key)
        for key in (
            "id",
            "order_id",
            "chat_session_id",
            "reason",
            "description",
            "contact_phone",
            "received",
            "currency",
            "status",
            "route_reason",
            "original_status",
            "review_note",
            "return_address",
            "return_due_at",
            "return_carrier",
            "return_tracking",
            "created_at",
            "refunded_at",
        )
    }
    session = (
        db.get(ChatSession, refund.chat_session_id) if refund.chat_session_id else None
    )
    result.update(
        amount=str(refund.amount),
        demo=True,
        human_status=session.human_status if session else "none",
        evidence=[
            {"id": e.id, "url": f"/api/shop/refund-evidence/{e.id}"}
            for e in db.scalars(
                select(RefundEvidence).where(RefundEvidence.refund_id == refund.id)
            )
        ],
        events=[
            {"action": e.action, "note": e.note, "created_at": e.created_at}
            for e in db.scalars(
                select(RefundEvent)
                .where(RefundEvent.refund_id == refund.id)
                .order_by(RefundEvent.id)
            )
        ],
    )
    return result
