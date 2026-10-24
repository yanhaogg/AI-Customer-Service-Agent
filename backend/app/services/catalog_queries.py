"""商品公共查询与数据组装，供商城、后台和 Agent 共用。

公共查询和数据组装供业务用例复用，本模块不提交事务。
"""

import logging
from fastapi import HTTPException
from app.storage import VISIBLE_STATUSES
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import distinct_on
from app.database.catalog_models import (
    CatalogCategory,
    Product,
    ProductImage,
    ProductPriceRecord,
)
from app.database.shop_models import SaleOffer

logger = logging.getLogger(__name__)


def execute(db, statement):
    """执行商品查询并统一转换数据库异常。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        statement: SQLAlchemy 可执行查询语句。

    输出：
        SQLAlchemy Result 查询结果；数据库异常时抛 HTTPException(503)。

    流程：
        1. 调用 db.execute
        2. 捕获 SQLAlchemyError 后回滚、记录日志并返回商品服务不可用错误；正常路径不提交。
    """
    try:
        return db.execute(statement)
    except SQLAlchemyError:
        db.rollback()
        logger.warning(
            "Catalog query failed; check database connection and imported tables"
        )
        raise HTTPException(
            503, "商品服务暂时不可用，请检查数据库连接和商品导入。"
        ) from None


def categories_data(db):
    """统计各分类中可见商品的数量。

    输入：
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        list[dict]：每项含 code、name、count；无可见商品的分类不返回。

    流程：
        1. 关联分类和商品
        2. 按可见状态过滤
        3. 分组计数并按分类编码排序
        4. 转为字典列表；不提交。
    """
    rows = execute(
        db,
        select(
            CatalogCategory.code,
            CatalogCategory.name,
            func.count(Product.id).label("count"),
        )
        .join(Product, Product.category_id == CatalogCategory.id)
        .where(Product.status.in_(VISIBLE_STATUSES))
        .group_by(CatalogCategory.id)
        .order_by(CatalogCategory.code),
    ).all()
    return [{"code": row.code, "name": row.name, "count": row.count} for row in rows]


def serialize_products(db, items):
    """批量将商品和分类查询行组装为商品摘要。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        items: 查询行序列，每行为 (Product, CatalogCategory)。

    输出：
        list[dict]：含名称、分类、主图、参考价格和演示销售 offer；空输入返回空列表。

    流程：
        1. 提取商品主键
        2. 批量查主图、每商品最新参考价格和销售设置
        3. 建映射
        4. 按输入顺序组装；金额转字符串，不提交。
    """
    if not items:
        return []
    ids = [product.id for product, _ in items]
    images = execute(
        db,
        select(ProductImage.product_id, ProductImage.asset_id, ProductImage.alt)
        .where(ProductImage.product_id.in_(ids))
        .order_by(
            ProductImage.product_id,
            ProductImage.is_primary.desc(),
            ProductImage.sort_order,
            ProductImage.id,
        ),
    ).all()
    primary = {}
    for image in images:
        primary.setdefault(
            image.product_id,
            {"url": f"/api/catalog/media/{image.asset_id}", "alt": image.alt},
        )
    # DISTINCT ON chooses one latest source price per product without duplicating product rows.
    prices = (
        execute(
            db,
            select(ProductPriceRecord)
            .where(ProductPriceRecord.product_id.in_(ids))
            .ext(distinct_on(ProductPriceRecord.product_id))
            .order_by(
                ProductPriceRecord.product_id,
                ProductPriceRecord.collected_at.desc(),
                ProductPriceRecord.id.desc(),
            ),
        )
        .scalars()
        .all()
    )
    price_map = {
        price.product_id: {
            "amount": str(price.amount),
            "currency": price.currency,
            "kind": price.price_kind,
            "observed_at": price.observed_at,
            "is_historical": price.price_kind == "historical_dataset_price",
        }
        for price in prices
    }
    offers = (
        execute(db, select(SaleOffer).where(SaleOffer.product_id.in_(ids)))
        .scalars()
        .all()
    )
    offer_map = {
        offer.product_id: {
            "amount": str(offer.price),
            "currency": offer.currency,
            "stock": offer.stock,
            "is_active": offer.is_active,
            "demo": True,
        }
        for offer in offers
    }
    return [
        {
            "id": product.id,
            "import_key": product.import_key,
            "name": product.name_zh or product.name_original,
            "name_original": product.name_original,
            "brand": product.brand,
            "model": product.model,
            "category": category.name,
            "category_code": category.code,
            "introduction": product.introduction_zh,
            "image": primary.get(product.id),
            "price": price_map.get(product.id),
            "offer": offer_map.get(product.id, {"is_active": False, "stock": 0}),
        }
        for product, category in items
    ]


def product_query():
    """创建仅包含可见商品的基础查询。

    输入：
        无。

    输出：
        SQLAlchemy Select，查询行结构为 (Product, CatalogCategory)。

    流程：
        1. 构造商品与分类连接
        2. 加 VISIBLE_STATUSES 条件
        3. 返回查询对象；此处不执行 SQL。
    """
    return (
        select(Product, CatalogCategory)
        .join(CatalogCategory, Product.category_id == CatalogCategory.id)
        .where(Product.status.in_(VISIBLE_STATUSES))
    )
