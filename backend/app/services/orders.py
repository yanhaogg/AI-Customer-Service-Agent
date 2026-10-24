"""结算预览、下单、订单查询及支付、取消、收货、发货状态转换。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, select
from app.database.shop_models import CartItem, ShopOrder, ShopOrderItem
from app.services.aftersales_queries import active_refund
from app.services.inventory import release_stock
from app.database.aftersales_models import ShipmentReminder
from app.services.shopping_queries import (
    address_data,
    owned_address,
    expire_orders,
    quote,
    order_data,
    owned_order,
)
from app.services.clock import now
from app.services.user_access import lock_user


def preview(body, db):
    """按数据库中的价格与库存计算结算预览。

    输入：
        body: PreviewBody：items 商品主键和数量列表。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items、total、currency、shipping_fee、demo。

    流程：
        1. 回收过期待付款订单
        2. quote 计算并校验
        3. 提交过期回收修改
        4. 返回报价；本次预览不扣库存、不创建订单。
    """
    expire_orders(db)
    result, _ = quote(db, body.items)
    db.commit()
    return result


def checkout(body, db, user):
    """创建待支付订单，在同一事务内预留库存和保存成交快照。

    输入：
        body: CheckoutBody：选品/预期价格、地址、购物车条目、备注和 request_key。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：新订单详情；相同 request_key 和内容的重试返回原订单。

    流程：
        1. 回收过期订单并锁用户
        2. 请求哈希去重
        3. 校验本人地址及购物车内容
        4. 锁销售行重新计价并比对前端预期价
        5. 建 30 分钟待支付订单及地址/商品快照
        6. 扣库存、移除已结算购物车项
        7. 提交。
    """
    # 下单顺序：回收过期订单 → 用户锁与幂等检查 → 校验地址/购物车 → 锁库存并计价。
    # 最后在同一事务内保存订单快照、预留库存和删除已结算购物车项，任一步失败则不提交。
    expire_orders(db)
    lock_user(db, user)
    # 同一 request_key 只能对应同一份结算内容；网络重试直接返回原订单，不重复扣库存。
    fingerprint = hashlib.sha256(
        json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    previous = db.scalar(
        select(ShopOrder).where(
            ShopOrder.user_id == user.id, ShopOrder.request_key == body.request_key
        )
    )
    if previous:
        if previous.request_hash != fingerprint:
            raise HTTPException(409, "重复请求编号对应不同订单，请刷新结算页面")
        result = order_data(db, previous)
        db.commit()
        return result
    address = owned_address(db, user, body.address_id)
    cart_entries = []
    if body.cart_item_ids:
        cart_entries = db.scalars(
            select(CartItem)
            .where(CartItem.user_id == user.id, CartItem.id.in_(body.cart_item_ids))
            .with_for_update()
        ).all()
        actual = {entry.product_id: entry.quantity for entry in cart_entries}
        if len(cart_entries) != len(body.cart_item_ids) or actual != {
            i.product_id: i.quantity for i in body.items
        }:
            raise HTTPException(409, "购物车已变化，请返回购物车重新结算")
    result, offers = quote(db, body.items, lock=True)
    for item in body.items:
        offer = offers[item.product_id]
        if item.expected_price != offer.price or item.currency != offer.currency:
            raise HTTPException(409, "商品价格已变化，请重新加载结算页面确认")
    # 保存地址、商品名和成交单价的快照，后续用户改地址或管理员改商品不会改写历史订单。
    order = ShopOrder(
        number="S" + now().strftime("%Y%m%d%H%M%S") + uuid4().hex[:10],
        user_id=user.id,
        request_key=body.request_key,
        request_hash=fingerprint,
        status="pending_payment",
        total=Decimal(result["total"]),
        currency=result["currency"],
        shipping_address={
            k: v
            for k, v in address_data(address).items()
            if k not in ("id", "is_default")
        },
        note=body.note,
        expires_at=now() + timedelta(minutes=30),
    )
    db.add(order)
    db.flush()
    for item in result["items"]:
        offers[item["product_id"]].stock -= item["quantity"]
        offers[item["product_id"]].updated_at = now()
        db.add(
            ShopOrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                name=item["name"],
                image_asset_id=item["image_asset_id"],
                quantity=item["quantity"],
                unit_price=Decimal(item["unit_price"]),
            )
        )
    for entry in cart_entries:
        db.delete(entry)
    db.flush()
    response = order_data(db, order)
    db.commit()
    return response


def orders(status, page, db, user):
    """分页读取本人订单。

    输入：
        status: str，状态筛选条件，具体允许值由路由约束。
        page: int，从 1 开始的页码（由路由校验）。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：items 订单详情、total、total_pages。

    流程：
        1. 回收过期订单
        2. 按 user.id 和可选 status 筛选
        3. 倒序每页取 10 条
        4. order_data 组装
        5. 提交回收修改。
    """
    expire_orders(db)
    query = select(ShopOrder).where(ShopOrder.user_id == user.id)
    if status:
        query = query.where(ShopOrder.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    data = db.scalars(
        query.order_by(ShopOrder.id.desc()).offset((page - 1) * 10).limit(10)
    ).all()
    result = {
        "items": [order_data(db, o) for o in data],
        "total": total,
        "total_pages": (total + 9) // 10,
    }
    db.commit()
    return result


def detail(order_id, db, user):
    """读取本人单个订单详情。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：订单字段、商品明细和最新售后摘要。

    流程：
        1. 回收过期订单
        2. owned_order 校验归属并锁订单
        3. order_data 组装
        4. 提交。
    """
    expire_orders(db)
    result = order_data(db, owned_order(db, user, order_id))
    db.commit()
    return result


def transition(order_id: int, action: str, db, user):
    """统一执行用户侧支付、取消、确认收货状态转换。

    输入：
        order_id: int，订单主键。
        action: str：pay（演示支付）、cancel（取消）、complete（确认收货）。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：转换后的订单详情；重复执行已达到的目标状态通常返回现状。

    流程：
        1. 校验 action
        2. 回收过期订单并锁本人订单
        3. 按当前状态判断能否转换
        4. 取消时释放库存，收货时检查活动退款
        5. 更新状态与时间
        6. flush、组装、提交；支付为演示状态更新。
    """
    # 集中处理支付、取消、确认收货的状态转换；先锁定订单，再检查当前状态和售后约束。
    if action not in ("pay", "cancel", "complete"):
        raise HTTPException(404, "操作不存在")
    expire_orders(db)
    order = owned_order(db, user, order_id)
    if action == "pay":
        if order.status == "paid":
            pass
        elif order.status != "pending_payment":
            raise HTTPException(409, "当前订单不可支付")
        elif order.expires_at <= now():
            raise HTTPException(409, "订单已超时，请刷新后重新下单")
        else:
            order.status = "paid"
            order.paid_at = now()
    elif action == "cancel":
        if order.status == "cancelled":
            pass
        elif order.status != "pending_payment":
            raise HTTPException(409, "仅待支付订单可以取消，其他售后请联系客服")
        else:
            release_stock(db, [order])
            order.status = "cancelled"
            order.cancelled_at = now()
            order.cancel_reason = "用户取消"
    else:
        if active_refund(db, order.id):
            raise HTTPException(409, "售后处理中，暂不能确认收货")
        if order.status == "completed":
            pass
        elif order.status != "shipped":
            raise HTTPException(409, "仅已发货订单可以确认收货")
        else:
            order.status = "completed"
            order.completed_at = now()
    db.flush()
    result = order_data(db, order)
    db.commit()
    return result


def pay(order_id, db, user):
    """执行本人订单的演示支付。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：支付后的订单详情。

    流程：
        1. 调用 transition(action=pay)；由其校验待支付状态与有效期、更新时间并提交。
    """
    return transition(order_id, "pay", db, user)


def cancel(order_id, db, user):
    """取消本人尚未支付的订单。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：取消后的订单详情。

    流程：
        1. 调用 transition(action=cancel)；由其校验状态、回补库存、写取消原因并提交。
    """
    return transition(order_id, "cancel", db, user)


def confirm_receipt(order_id, db, user):
    """确认本人已发货订单收货。

    输入：
        order_id: int，订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：确认后的订单详情。

    流程：
        1. 调用 transition(action=complete)；由其检查活动退款和已发货状态、写完成时间并提交。
    """
    return transition(order_id, "complete", db, user)


def admin_orders(status, q, page, db):
    """为后台按状态和订单号检索全部订单。

    输入：
        status: str，状态筛选条件，具体允许值由路由约束。
        q: str，搜索关键词，可为空。
        page: int，从 1 开始的页码（由路由校验）。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items（订单详情加 user_id）、total、total_pages。

    流程：
        1. 回收过期订单
        2. 按可选 status 和转义订单号关键词过滤
        3. 倒序每页取 10 条
        4. 组装详情并提交；管理员权限由路由校验。
    """
    expire_orders(db)
    query = select(ShopOrder)
    if status:
        query = query.where(ShopOrder.status == status)
    if q.strip():
        query = query.where(ShopOrder.number.icontains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    data = db.scalars(
        query.order_by(ShopOrder.id.desc()).offset((page - 1) * 10).limit(10)
    ).all()
    result = {
        "items": [{**order_data(db, o), "user_id": o.user_id} for o in data],
        "total": total,
        "total_pages": (total + 9) // 10,
    }
    db.commit()
    return result


def ship(order_id, body, db):
    """为已支付订单登记发货物流。

    输入：
        order_id: int，订单主键。
        body: ShippingBody：carrier 快递公司、tracking_number 单号。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：发货后的订单详情。

    流程：
        1. 锁订单
        2. 校验存在、paid 状态、无活动退款和快递公司非空
        3. 写 shipped、物流和时间
        4. 将待处理催发货改已处理
        5. flush、组装、提交。
    """
    # 发货由管理员接口执行；订单状态和进行中的退款都要检查，AI 查询工具没有此能力。
    order = db.scalar(
        select(ShopOrder).where(ShopOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise HTTPException(404, "订单不存在")
    if order.status != "paid":
        raise HTTPException(409, "仅已支付订单可以发货")
    if active_refund(db, order.id):
        raise HTTPException(409, "退款审核或退货处理中，不能发货")
    if not body.carrier.strip():
        raise HTTPException(422, "快递公司不能为空")
    order.status = "shipped"
    order.carrier = body.carrier.strip()
    order.tracking_number = body.tracking_number
    order.shipped_at = now()
    for reminder in db.scalars(
        select(ShipmentReminder).where(
            ShipmentReminder.order_id == order.id, ShipmentReminder.status == "pending"
        )
    ):
        reminder.status = "handled"
        reminder.handled_note = "订单已发货"
        reminder.handled_at = now()
    db.flush()
    result = order_data(db, order)
    db.commit()
    return result
