"""管理员维护独立的演示销售价格、库存与上架状态。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import select
from app.database.catalog_models import Product
from app.database.shop_models import SaleOffer
from app.storage import VISIBLE_STATUSES
from app.services.clock import now


def get_offer(product_id, db):
    """读取商品独立的演示销售配置。

    输入：
        product_id: int，商品主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：offer 为售价、币种、库存、上架标记和更新时间字典或 None，demo=True。

    流程：
        1. 按商品主键获取 SaleOffer
        2. 存在则提取字段，不存在返回 offer=None；不提交，也不在此校验商品存在。
    """
    offer = db.get(SaleOffer, product_id)
    return {
        "offer": (
            {
                key: getattr(offer, key)
                for key in ("price", "currency", "stock", "is_active", "updated_at")
            }
            if offer
            else None
        ),
        "demo": True,
    }


def set_offer(product_id, body, db):
    """创建或更新演示销售价格、库存和上架状态。

    输入：
        product_id: int，商品主键。
        body: OfferBody：price、currency、stock、is_active 及原 updated_at。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：get_offer 返回的销售设置及 demo 标记。

    流程：
        1. 共享锁校验可见商品
        2. 锁销售行
        3. 用 updated_at 校验编辑版本（冲突 409）→ 新建或更新字段和时间
        4. flush、组装、提交；不修改参考价格历史。
    """
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.status.in_(VISIBLE_STATUSES))
        .with_for_update(read=True)
    )
    if product is None:
        raise HTTPException(404, "商品不存在或已删除")
    offer = db.scalar(
        select(SaleOffer).where(SaleOffer.product_id == product_id).with_for_update()
    )
    if (offer and body.updated_at != offer.updated_at) or (
        not offer and body.updated_at is not None
    ):
        raise HTTPException(409, "库存或售价已变化，请重新加载销售设置")
    if offer is None:
        offer = SaleOffer(product_id=product_id)
        db.add(offer)
    for key in ("price", "currency", "stock", "is_active"):
        setattr(offer, key, getattr(body, key))
    offer.updated_at = now()
    db.flush()
    result = get_offer(product_id, db)
    db.commit()
    return result
