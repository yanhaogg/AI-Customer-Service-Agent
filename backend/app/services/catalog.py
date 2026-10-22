"""公开商品分类、列表、详情及媒体访问校验。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

import logging
from fastapi import HTTPException
from app.storage import MATERIALS_ROOT
from sqlalchemy import func, or_, select
from app.database.catalog_models import (
    CatalogCategory,
    MediaAsset,
    Product,
    ProductPriceRecord,
)
from app.services.catalog_queries import (
    execute,
    categories_data,
    serialize_products,
    product_query,
)

logger = logging.getLogger(__name__)


def categories(db):
    return {"items": categories_data(db)}


def products(category, q, sort, page, page_size, db):
    query = product_query()
    if category:
        query = query.where(CatalogCategory.code == category)
    if q.strip():
        # Treat user-entered percent/underscore literally rather than as SQL wildcards.
        query = query.where(
            or_(
                *[
                    column.icontains(q.strip(), autoescape=True)
                    for column in (
                        Product.name_original,
                        Product.name_zh,
                        Product.brand,
                        Product.model,
                        Product.introduction_zh,
                    )
                ]
            )
        )
    total = execute(db, select(func.count()).select_from(query.subquery())).scalar_one()
    if sort != "recommended":
        latest_price = (
            select(ProductPriceRecord.amount)
            .where(ProductPriceRecord.product_id == Product.id)
            .order_by(
                ProductPriceRecord.collected_at.desc(), ProductPriceRecord.id.desc()
            )
            .limit(1)
            .scalar_subquery()
        )
        query = query.order_by(
            (
                latest_price.asc().nulls_last()
                if sort == "price_asc"
                else latest_price.desc().nulls_last()
            ),
            Product.id,
        )
    else:
        query = query.order_by(Product.id)
    rows = execute(db, query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": serialize_products(db, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def product_detail(product_id, db):
    row = execute(db, product_query().where(Product.id == product_id)).first()
    if not row:
        raise HTTPException(404, "没有找到这款商品")
    result = serialize_products(db, [row])[0]
    product, category = row
    result.update(
        description_original=product.description_original,
        specs=product.specs or {},
        quality=product.quality or {},
    )
    related = execute(
        db,
        product_query()
        .where(Product.category_id == category.id, Product.id != product_id)
        .order_by(Product.id)
        .limit(4),
    ).all()
    result["related"] = serialize_products(db, related)
    return result


def media(asset_id, db):
    asset = execute(
        db, select(MediaAsset).where(MediaAsset.id == asset_id)
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(404, "图片不存在")
    path = (MATERIALS_ROOT / asset.storage_key).resolve()
    if not path.is_relative_to(MATERIALS_ROOT) or not path.is_file():
        raise HTTPException(404, "图片文件不存在")
    return path, asset.content_type
