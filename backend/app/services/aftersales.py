"""退款用例：申请、撤销、退货物流、人工审核及完成退款。

执行顺序由这里组织；规则见 refund_policy，读取见 aftersales_queries。
公开业务用例负责提交；complete_refund 等辅助步骤不提交，由所属用例统一管理事务。
"""

import hashlib
import json
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.database.shop_models import ShopOrder
from app.database.aftersales_models import RefundRequest, RefundEvidence, RefundEvent
from .clock import now
from .refund_policy import REASONS, refund_policy, auto_route
from .aftersales_queries import active_refund, refund_data
from .order_access import owned
from .conversations import order_session
from .inventory import release_stock


def event(db, refund, user_id, action, note):
    db.add(RefundEvent(refund_id=refund.id, actor_id=user_id, action=action, note=note))
    refund.updated_at = now()


def complete_refund(db, order, refund, user_id, note):
    # 统一完成演示退款并记录事件；未发货订单只回补一次库存，已发货商品不自动恢复可售。
    if refund.status == "refunded":
        return
    if order.status == "refunded":
        raise ValueError("Order already refunded")
    if refund.original_status == "paid" and not refund.stock_restored:
        release_stock(db, [order])
        refund.stock_restored = True
    # Returned or lost shipped goods are not automatically made saleable again.
    order.status = "refunded"
    order.refunded_at = now()
    refund.status = "refunded"
    refund.refunded_at = now()
    event(db, refund, user_id, "refunded", note + "（模拟退款，无真实扣款或转账）")


def locked_refund(db, refund_id, user=None):
    query = select(RefundRequest).where(RefundRequest.id == refund_id)
    if user:
        query = query.where(RefundRequest.user_id == user.id)
    refund = db.scalar(query)
    if refund is None:
        raise HTTPException(404, "退款申请不存在")
    order = db.scalar(
        select(ShopOrder).where(ShopOrder.id == refund.order_id).with_for_update()
    )
    refund = db.scalar(
        query.with_for_update().execution_options(populate_existing=True)
    )
    return order, refund


def options(order_id, db, user):
    order = owned(db, user, order_id)
    result = {
        **refund_policy(),
        "can_apply": order.status in ("paid", "shipped", "completed")
        and active_refund(db, order.id) is None,
        "auto_possible": auto_route(order, "not_needed", False),
        "order_status": order.status,
        "contact_phone": (order.shipping_address or {}).get("phone", ""),
    }
    db.commit()
    return result


def refunds(order_id, db, user):
    order = owned(db, user, order_id)
    result = {
        "items": [
            refund_data(db, r)
            for r in db.scalars(
                select(RefundRequest)
                .where(RefundRequest.order_id == order.id)
                .order_by(RefundRequest.id.desc())
            )
        ]
    }
    db.commit()
    return result


def apply_refund(order_id, body, db, user):
    # 1. 先校验归属并锁订单，再处理重复请求；重试不能重复创建申请或恢复库存。
    order = owned(db, user, order_id)
    fingerprint = hashlib.sha256(
        json.dumps({"order_id": order_id, **body.model_dump()}, sort_keys=True).encode()
    ).hexdigest()
    previous = db.scalar(
        select(RefundRequest).where(
            RefundRequest.user_id == user.id,
            RefundRequest.request_key == body.request_key,
        )
    )
    if previous:
        if previous.request_hash != fingerprint:
            raise HTTPException(409, "重复请求编号对应不同申请，请重新填写")
        result = refund_data(db, previous)
        db.commit()
        return result
    # 2. 校验当前业务状态和用户提供的材料，任何失败都不会提交本次事务。
    if order.status not in ("paid", "shipped", "completed"):
        raise HTTPException(
            409, "仅已支付、已发货或已完成订单可以申请退款；待支付请取消订单"
        )
    if active_refund(db, order.id):
        raise HTTPException(409, "该订单已有进行中的退款申请")
    if (order.status == "paid" and body.received) or (
        order.status == "completed" and not body.received
    ):
        raise HTTPException(422, "收到货状态与当前订单不一致，请联系客服核实")
    if body.reason == "not_received" and body.received:
        raise HTTPException(422, "已收到货不能选择未收到货原因")
    if len(body.evidence_ids) != len(set(body.evidence_ids)):
        raise HTTPException(422, "凭证不能重复")
    evidence = db.scalars(
        select(RefundEvidence)
        .where(
            RefundEvidence.id.in_(body.evidence_ids),
            RefundEvidence.user_id == user.id,
            RefundEvidence.order_id == order.id,
            RefundEvidence.refund_id.is_(None),
        )
        .with_for_update()
    ).all()
    if len(evidence) != len(body.evidence_ids):
        raise HTTPException(422, "部分凭证不属于本订单或已被使用")
    if body.reason in ("quality", "damaged") and not evidence:
        raise HTTPException(422, "质量或破损问题请上传至少1张照片")
    # 3. 纯规则决定自动/人工分支；会话服务只负责关联订单会话与人工接管。
    automatic = auto_route(order, body.reason, body.received)
    session = order_session(db, order, "refund", human=not automatic)
    refund = RefundRequest(
        order_id=order.id,
        user_id=user.id,
        chat_session_id=session.id,
        request_key=body.request_key,
        request_hash=fingerprint,
        reason=body.reason,
        description=body.description,
        contact_phone=body.contact_phone,
        received=body.received,
        amount=order.total,
        currency=order.currency,
        status="review_pending",
        original_status=order.status,
        route_reason=(
            "未发货且支付24小时内的普通整单退款，自动处理"
            if automatic
            else "需要人工核验发货、收货、申请时效或异常原因"
        ),
    )
    # 4. 保存申请和凭证关联；flush 取得主键，用例结束时再统一 commit。
    db.add(refund)
    db.flush()
    for e in evidence:
        e.refund_id = refund.id
    event(db, refund, user.id, "submitted", f"申请整单退款：{REASONS[body.reason]}")
    # 5. 自动分支当场完成模拟退款；人工分支保留 review_pending 等待审核。
    if automatic:
        complete_refund(db, order, refund, user.id, "符合自动退款规则")
    db.flush()
    result = refund_data(db, refund)
    db.commit()
    return result


def withdraw(refund_id, db, user):
    order, refund = locked_refund(db, refund_id, user)
    if refund.status not in ("review_pending", "awaiting_return"):
        raise HTTPException(409, "当前阶段不能撤销，请联系人工客服")
    refund.status = "withdrawn"
    event(db, refund, user.id, "withdrawn", "用户撤销退款申请")
    db.flush()
    result = refund_data(db, refund)
    db.commit()
    return result


def return_shipping(refund_id, body, db, user):
    order, refund = locked_refund(db, refund_id, user)
    if refund.status != "awaiting_return":
        raise HTTPException(409, "请先等待客服审核并提供退货地址")
    if not body.carrier.strip():
        raise HTTPException(422, "快递公司不能为空")
    refund.status = "return_in_transit"
    refund.return_carrier = body.carrier.strip()
    refund.return_tracking = body.tracking_number
    event(db, refund, user.id, "return_shipped", "用户提交退货物流，等待客服验收")
    db.flush()
    result = refund_data(db, refund)
    db.commit()
    return result


def review(refund_id, body, db, user):
    # 审核流程：拒绝 / 批准后等待退货 / 直接完成退款 / 确认退货验收。
    order, refund = locked_refund(db, refund_id)
    if refund.status == "refunded" and body.action in ("approve", "confirm_return"):
        result = refund_data(db, refund)
        db.commit()
        return result
    if body.action == "reject":
        if refund.status != "review_pending":
            raise HTTPException(409, "仅待审核申请可以驳回")
        refund.status = "rejected"
        event(db, refund, user.id, "rejected", body.note)
    elif body.action == "approve":
        if refund.status != "review_pending":
            raise HTTPException(409, "该申请不在待审核阶段")
        if refund.received and refund.original_status in ("shipped", "completed"):
            if len(body.return_address.strip()) < 10:
                raise HTTPException(422, "请填写至少10字的完整退货地址和联系人")
            refund.status = "awaiting_return"
            refund.return_address = body.return_address.strip()
            refund.return_due_at = now() + timedelta(days=7)
            event(db, refund, user.id, "return_authorized", body.note)
        else:
            complete_refund(db, order, refund, user.id, body.note)
    else:
        if refund.status != "return_in_transit":
            raise HTTPException(409, "仅已寄回的申请可以确认验收退款")
        complete_refund(db, order, refund, user.id, "客服确认退货验收：" + body.note)
    refund.reviewer_id = user.id
    refund.review_note = body.note
    db.flush()
    result = refund_data(db, refund)
    db.commit()
    return result


def admin_refunds(order_id, db):
    if db.get(ShopOrder, order_id) is None:
        raise HTTPException(404, "订单不存在")
    return {
        "items": [
            refund_data(db, r)
            for r in db.scalars(
                select(RefundRequest)
                .where(RefundRequest.order_id == order_id)
                .order_by(RefundRequest.id.desc())
            )
        ]
    }
