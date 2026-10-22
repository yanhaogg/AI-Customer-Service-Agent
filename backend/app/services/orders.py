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
    expire_orders(db)
    result, _ = quote(db, body.items)
    db.commit()
    return result


def checkout(body, db, user):
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
    expire_orders(db)
    result = order_data(db, owned_order(db, user, order_id))
    db.commit()
    return result


def transition(order_id: int, action: str, db, user):
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
    return transition(order_id, "pay", db, user)


def cancel(order_id, db, user):
    return transition(order_id, "cancel", db, user)


def confirm_receipt(order_id, db, user):
    return transition(order_id, "complete", db, user)


def admin_orders(status, q, page, db):
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
