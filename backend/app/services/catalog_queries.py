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
    return (
        select(Product, CatalogCategory)
        .join(CatalogCategory, Product.category_id == CatalogCategory.id)
        .where(Product.status.in_(VISIBLE_STATUSES))
    )
