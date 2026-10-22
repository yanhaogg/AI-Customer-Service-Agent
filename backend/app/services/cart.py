"""购物车条目增删改查；结算仍由订单服务执行。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from app.database.catalog_models import Product
from app.database.shop_models import CartItem
from app.services.catalog_queries import product_query, serialize_products
from app.schemas.shop import Selection
from app.services.shopping_queries import expire_orders, quote
from app.services.user_access import lock_user


def cart(db, user):
    expire_orders(db)
    rows = db.scalars(
        select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.id.desc())
    ).all()
    ids = [item.product_id for item in rows]
    visible = {
        p["id"]: p
        for p in serialize_products(
            db, db.execute(product_query().where(Product.id.in_(ids))).all()
        )
    }
    result = {
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "product": visible.get(item.product_id),
                "available": bool(
                    visible.get(item.product_id)
                    and visible[item.product_id].get("offer", {}).get("is_active")
                ),
            }
            for item in rows
        ]
    }
    db.commit()
    return result


def add_cart(body, db, user):
    lock_user(db, user)
    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.product_id == body.product_id
        )
    )
    quantity = body.quantity + (item.quantity if item else 0)
    if quantity > 99:
        raise HTTPException(422, "同款商品最多加入 99 件")
    if (
        item is None
        and db.scalar(
            select(func.count())
            .select_from(CartItem)
            .where(CartItem.user_id == user.id)
        )
        >= 100
    ):
        raise HTTPException(422, "购物车最多保存 100 款商品")
    quote(db, [Selection(product_id=body.product_id, quantity=quantity)])
    if item:
        item.quantity = quantity
    else:
        item = CartItem(user_id=user.id, product_id=body.product_id, quantity=quantity)
        db.add(item)
    db.flush()
    result = {"id": item.id, "quantity": item.quantity}
    db.commit()
    return result


def update_cart(item_id, body, db, user):
    lock_user(db, user)
    item = db.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user.id)
    )
    if item is None:
        raise HTTPException(404, "购物车条目不存在")
    quote(db, [Selection(product_id=item.product_id, quantity=body.quantity)])
    item.quantity = body.quantity
    db.commit()
    return {"quantity": body.quantity}


def delete_cart(item_id, db, user):
    lock_user(db, user)
    item = db.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user.id)
    )
    if item is None:
        raise HTTPException(404, "购物车条目不存在")
    db.delete(item)
    db.commit()
