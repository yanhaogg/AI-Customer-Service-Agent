"""订单归属校验与加锁；写流程统一先锁订单，再锁关联业务记录。"""

from fastapi import HTTPException
from sqlalchemy import select
from app.database.shop_models import ShopOrder


def owned(db, user, order_id):
    order = db.scalar(
        select(ShopOrder)
        .where(ShopOrder.id == order_id, ShopOrder.user_id == user.id)
        .with_for_update()
    )
    if order is None:
        raise HTTPException(404, "订单不存在")
    return order
