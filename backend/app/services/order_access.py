"""订单归属校验与加锁；写流程统一先锁订单，再锁关联业务记录。"""

from fastapi import HTTPException
from sqlalchemy import select
from app.database.shop_models import ShopOrder


def owned(db, user, order_id):
    """校验当前用户对订单的归属并锁定订单。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        order_id: int，订单主键。

    输出：
        ShopOrder ORM 对象；不存在或不属于用户时抛 404。

    流程：
        1. 按 order_id 和 user.id 查询
        2. 使用 FOR UPDATE 锁订单
        3. 返回对象；不提交，供售后等写流程复用。
    """
    order = db.scalar(
        select(ShopOrder)
        .where(ShopOrder.id == order_id, ShopOrder.user_id == user.id)
        .with_for_update()
    )
    if order is None:
        raise HTTPException(404, "订单不存在")
    return order
