"""当前用户浏览历史的记录、查询和清除。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

import logging
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from app.database.catalog_models import Product, ProductImage
from app.database.activity_models import BrowsingHistory
from app.storage import VISIBLE_STATUSES
from app.services.catalog_queries import product_query, serialize_products
from app.services.clock import now
from app.services.user_access import lock_user

logger = logging.getLogger(__name__)


def record_browse(body, db, user):
    # 只保存已登录用户主动浏览的商品；合并重复记录，更新浏览次数与最近浏览时间。
    lock_user(db, user)
    product = db.scalar(
        select(Product).where(
            Product.id == body.product_id, Product.status.in_(VISIBLE_STATUSES)
        )
    )
    if product is None:
        raise HTTPException(404, "商品不存在或已删除")
    image = db.scalar(
        select(ProductImage.asset_id)
        .where(ProductImage.product_id == product.id)
        .order_by(
            ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id
        )
        .limit(1)
    )
    entry = db.scalar(
        select(BrowsingHistory).where(
            BrowsingHistory.user_id == user.id, BrowsingHistory.product_id == product.id
        )
    )
    if entry is None:
        entry = BrowsingHistory(
            user_id=user.id,
            product_id=product.id,
            product_name=product.name_zh or product.name_original,
            image_asset_id=image,
            view_count=1,
            last_visit_key=body.visit_key,
        )
        db.add(entry)
    elif entry.last_visit_key != body.visit_key:
        entry.view_count += 1
        entry.last_visit_key = body.visit_key
        entry.last_viewed_at = now()
    entry.product_name = product.name_zh or product.name_original
    entry.image_asset_id = image
    db.flush()
    # Keep the most recent 500 distinct products per user.
    stale = (
        select(BrowsingHistory.id)
        .where(BrowsingHistory.user_id == user.id)
        .order_by(BrowsingHistory.last_viewed_at.desc(), BrowsingHistory.id.desc())
        .offset(500)
    )
    db.execute(delete(BrowsingHistory).where(BrowsingHistory.id.in_(stale)))
    result = {"id": entry.id, "view_count": entry.view_count}
    db.commit()
    return result


def browsing(page, db, user):
    query = select(BrowsingHistory).where(BrowsingHistory.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(BrowsingHistory.last_viewed_at.desc(), BrowsingHistory.id.desc())
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    products = {
        p["id"]: p
        for p in serialize_products(
            db,
            db.execute(
                product_query().where(Product.id.in_([r.product_id for r in rows]))
            ).all(),
        )
    }
    return {
        "items": [
            {
                "id": r.id,
                "product_id": r.product_id,
                "name": r.product_name,
                "view_count": r.view_count,
                "last_viewed_at": r.last_viewed_at,
                "available": r.product_id in products,
                "product": products.get(r.product_id),
                "image": (
                    {"url": f"/api/catalog/media/{r.image_asset_id}"}
                    if r.image_asset_id
                    else None
                ),
            }
            for r in rows
        ],
        "total": total,
        "total_pages": (total + 19) // 20,
    }


def clear_browsing(db, user):
    lock_user(db, user)
    db.execute(delete(BrowsingHistory).where(BrowsingHistory.user_id == user.id))
    db.commit()


def delete_browse(entry_id, db, user):
    lock_user(db, user)
    entry = db.scalar(
        select(BrowsingHistory).where(
            BrowsingHistory.id == entry_id, BrowsingHistory.user_id == user.id
        )
    )
    if entry is None:
        raise HTTPException(404, "浏览记录不存在")
    db.delete(entry)
    db.commit()
