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
    """记录退款操作事件并更新申请时间。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        refund: RefundRequest ORM 对象。
        user_id: int，当前操作者的用户主键。
        action: str，退款事件动作编码。
        note: str，操作说明或事件备注。

    输出：
        None；向 Session 添加 RefundEvent，并修改 refund.updated_at。

    流程：
        1. 用申请主键和操作者信息创建事件
        2. 更新申请时间；不 commit，由上层用例提交。
    """
    db.add(RefundEvent(refund_id=refund.id, actor_id=user_id, action=action, note=note))
    refund.updated_at = now()


def complete_refund(db, order, refund, user_id, note):
    """完成演示退款，并按条件回补未发货订单库存。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order: ShopOrder ORM 对象。
        refund: RefundRequest ORM 对象。
        user_id: int，当前操作者的用户主键。
        note: str，操作说明或事件备注。

    输出：
        None；原地修改订单、退款及事件；已退款申请直接返回。

    流程：
        1. 检查重复退款
        2. 仅原状态 paid 且尚未回补时释放库存
        3. 将订单和申请改为 refunded
        4. 记模拟退款事件；不提交，无真实转账。
    """
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
    """读取退款及订单并按固定顺序加锁。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        refund_id: int，退款申请主键。
        user: User 或 None；提供时限制申请归属，None 用于已验证权限的管理员入口。

    输出：
        tuple：(ShopOrder, RefundRequest)，均为 ORM 对象。

    流程：
        1. 查询申请（可按 user 限定归属，未找到返回 404）→ 先锁订单
        2. 再锁申请并刷新已有对象；不提交，锁随事务释放。
    """
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
    """获取订单可用的退款选项和政策。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：退款政策、can_apply、auto_possible、order_status、contact_phone。

    流程：
        1. 校验归属并锁订单
        2. 判断可申请状态及有无活动退款
        3. 计算普通未收货原因的自动处理可能性
        4. 提交并返回。
    """
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
    """查询本人订单的退款申请历史。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：items 为按申请主键倒序排列的退款详情。

    流程：
        1. 校验订单归属并加锁
        2. 查该订单申请
        3. 逐条调用 refund_data
        4. 提交并返回。
    """
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
    """为本人订单创建可重试的整单退款申请。

    输入：
        order_id: int，订单主键。
        body: RefundCreate：原因、说明、电话、收货标记、凭证主键列表和 request_key。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：新申请或幂等重试命中的原申请详情。

    流程：
        1. 锁本人订单
        2. 用 request_key 和请求哈希去重
        3. 校验订单、收货状态和凭证归属
        4. 按规则选择自动或人工
        5. 复用订单会话
        6. 保存申请、关联凭证和事件
        7. 自动分支完成模拟退款
        8. 提交。
    """
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
    """撤销本人尚在允许撤销阶段的退款。

    输入：
        refund_id: int，退款申请主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：撤销后的退款详情。

    流程：
        1. 锁订单和本人申请
        2. 仅允许 review_pending 或 awaiting_return，否则 409
        3. 更新 withdrawn 并记事件
        4. flush、组装详情、提交。
    """
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
    """保存用户寄回商品的物流信息。

    输入：
        refund_id: int，退款申请主键。
        body: ReturnShipping：carrier 快递公司、tracking_number 退货单号。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：更新后的退款详情。

    流程：
        1. 锁订单和本人申请
        2. 要求 awaiting_return 且快递公司非空
        3. 保存公司及单号并改为 return_in_transit
        4. 记事件、flush、提交。
    """
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
    """执行管理员的退款审核或退货验收。

    输入：
        refund_id: int，退款申请主键。
        body: Review：action（reject/approve/confirm_return）、note、return_address。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：审核后的退款详情；已完成的批准/验收重试返回原详情。

    流程：
        1. 锁订单和申请
        2. 按 action 拒绝、批准或验收
        3. 已收货批准进入等待退货并设置地址/期限，其余批准或验收完成模拟退款
        4. 记录审核人、备注和事件
        5. 提交；权限由路由校验。
    """
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
    """查询指定订单的全部退款申请供后台展示。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items 为申请详情列表。

    流程：
        1. 确认订单存在（否则 404）→ 按申请主键倒序查询
        2. 调用 refund_data；不提交，管理员权限由路由校验。
    """
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
