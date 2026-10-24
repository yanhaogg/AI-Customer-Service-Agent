"""库存释放服务，供取消、超时回收和未发货退款共用。"""

from collections import defaultdict
from sqlalchemy import select
from app.database.shop_models import SaleOffer, ShopOrderItem
from .clock import now


def release_stock(db, orders):
    """将指定订单占用的商品数量加回销售库存。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        orders: ShopOrder 对象集合，调用方已验证可以释放库存。

    输出：
        None；修改对应 SaleOffer 的 stock 和 updated_at。

    流程：
        1. 按订单主键查询明细并按商品汇总数量
        2. 按商品主键固定顺序锁销售行
        3. 累加库存；不提交。调用方须保证订单符合释放条件且不会重复释放。
    """
    # 按商品汇总待释放数量，再按固定顺序锁库存行，减少并发订单之间的锁冲突。
    quantities = defaultdict(int)
    for item in db.scalars(
        select(ShopOrderItem).where(ShopOrderItem.order_id.in_([o.id for o in orders]))
    ):
        quantities[item.product_id] += item.quantity
    if quantities:
        for offer in db.scalars(
            select(SaleOffer)
            .where(SaleOffer.product_id.in_(quantities))
            .order_by(SaleOffer.product_id)
            .with_for_update()
        ):
            offer.stock += quantities[offer.product_id]
            offer.updated_at = now()
