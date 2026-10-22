"""库存释放服务，供取消、超时回收和未发货退款共用。"""

from collections import defaultdict
from sqlalchemy import select
from app.database.shop_models import SaleOffer, ShopOrderItem
from .clock import now


def release_stock(db, orders):
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
