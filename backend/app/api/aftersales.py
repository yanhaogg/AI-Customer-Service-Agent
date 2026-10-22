"""售后 HTTP 入口：参数/权限依赖 → 调用业务用例 → 返回结果。

业务判断、ORM 查询和事务在 services 中；保持现有 URL 和响应结构。
"""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_superadmin
from app.database.models import User
from app.database.session import get_db
from app.storage import MATERIALS_ROOT
from app.services import aftersales, order_support, refund_evidence
from app.schemas.aftersales import (
    Contact,
    Reminder,
    RefundCreate,
    EvidenceUpload,
    Review,
    ReturnShipping,
    HandleReminder,
)

router = APIRouter(
    prefix="/api/shop",
    tags=["order-aftersales"],
    dependencies=[Depends(get_current_user)],
)
admin_router = APIRouter(
    prefix="/api/admin",
    tags=["refund-review"],
    dependencies=[Depends(require_superadmin)],
)


@router.post("/orders/{order_id}/contact")
def contact(
    order_id: int,
    body: Contact,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = order_support.contact(order_id, body, db, user)
    return result


@router.post("/orders/{order_id}/remind-shipping")
def remind(
    order_id: int,
    body: Reminder,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = order_support.remind(order_id, body, db, user)
    return result


@router.get("/orders/{order_id}/refund-options")
def options(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    result = aftersales.options(order_id, db, user)
    return result


@router.get("/orders/{order_id}/refunds")
def refunds(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    result = aftersales.refunds(order_id, db, user)
    return result


@router.post("/orders/{order_id}/refunds", status_code=201)
def apply_refund(
    order_id: int,
    body: RefundCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = aftersales.apply_refund(order_id, body, db, user)
    return result


@router.post("/orders/{order_id}/refund-evidence", status_code=201)
def upload_evidence(
    order_id: int,
    body: EvidenceUpload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = refund_evidence.upload_evidence(order_id, body, db, user, MATERIALS_ROOT)
    return result


@router.get("/refund-evidence/{evidence_id}")
def evidence_file(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    path = refund_evidence.evidence_file(evidence_id, db, user, MATERIALS_ROOT)
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"}
    )


@router.post("/refunds/{refund_id}/withdraw")
def withdraw(
    refund_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = aftersales.withdraw(refund_id, db, user)
    return result


@router.post("/refunds/{refund_id}/return-shipping")
def return_shipping(
    refund_id: int,
    body: ReturnShipping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = aftersales.return_shipping(refund_id, body, db, user)
    return result


@admin_router.post("/refunds/{refund_id}/review")
def review(
    refund_id: int,
    body: Review,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    result = aftersales.review(refund_id, body, db, user)
    return result


@admin_router.post("/reminders/{reminder_id}/handle")
def handle_reminder(
    reminder_id: int, body: HandleReminder, db: Session = Depends(get_db)
):
    result = order_support.handle_reminder(reminder_id, body, db)
    return result


@admin_router.get("/orders/{order_id}/refunds")
def admin_refunds(order_id: int, db: Session = Depends(get_db)):
    result = aftersales.admin_refunds(order_id, db)
    return result
