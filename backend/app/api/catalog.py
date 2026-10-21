"""Read-only catalog endpoints backed by PostgreSQL and local image assets."""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import distinct_on

from app.database.catalog_models import (
    CatalogCategory,
    MediaAsset,
    Product,
    ProductImage,
    ProductPriceRecord,
)
from app.database.session import get_db
from app.database.homepage_models import HomepageConfig
from app.database.shop_models import SaleOffer

router = APIRouter(prefix="/api/catalog", tags=["catalog"])
logger = logging.getLogger(__name__)
MATERIALS_ROOT = Path(
    os.getenv("PRODUCT_MATERIALS_ROOT")
    or Path(__file__).resolve().parents[3] / "product_materials"
).resolve()
# Include imported draft records for this local material showcase; this is not a sale/checkout API.
VISIBLE_STATUSES = ("draft", "reviewed", "published")


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


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    return {"items": categories_data(db)}


@router.get("/products")
def products(
    category: str | None = None,
    q: str = Query("", max_length=150),
    sort: str = Query("recommended", pattern="^(recommended|price_asc|price_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
):
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


def default_home_data(db):
    categories = categories_data(db)
    total = sum(category["count"] for category in categories)
    if not total:
        return {
            "hero": None,
            "spotlights": [],
            "featured": [],
            "categories": [],
            "total": 0,
        }
    # Prefer a recognizable audio item with an actual local image as the homepage representative.
    hero_query = product_query().where(CatalogCategory.code == "05_audio")
    hero_rank = case(
        (Product.brand == "Marshall", 0),
        (Product.brand == "JBL", 1),
        (Product.brand == "Harman Kardon", 2),
        else_=3,
    )
    hero = execute(db, hero_query.order_by(hero_rank, Product.id).limit(1)).first()
    if hero is None:
        hero = execute(db, product_query().order_by(Product.id).limit(1)).first()
    selected_ids = [hero[0].id]
    spotlights = []
    for category in ["01_phones", "02_computers"]:
        rank = (
            case(
                (Product.brand == "Samsung", 0), (Product.brand == "Apple", 1), else_=2
            )
            if category == "01_phones"
            else case(
                (Product.name_original.icontains("laptop"), 0),
                (Product.name_original.icontains("MacBook"), 1),
                else_=2,
            )
        )
        item = execute(
            db,
            product_query()
            .where(CatalogCategory.code == category, Product.id.not_in(selected_ids))
            .order_by(rank, Product.id)
            .limit(1),
        ).first()
        if item:
            spotlights.append(item)
            selected_ids.append(item[0].id)
    featured = []
    for category in [
        "03_tablets",
        "06_wearables",
        "07_smart_home",
        "08_cameras",
        "09_networking",
        "10_storage",
        "11_power",
        "12_peripherals",
    ]:
        item = execute(
            db,
            product_query()
            .where(CatalogCategory.code == category, Product.id.not_in(selected_ids))
            .order_by(Product.id)
            .limit(1),
        ).first()
        if item:
            featured.append(item)
            selected_ids.append(item[0].id)
    return {
        "hero": serialize_products(db, [hero])[0],
        "spotlights": serialize_products(db, spotlights),
        "featured": serialize_products(db, featured),
        "categories": categories,
        "total": total,
    }


def configured_home_data(db, config):
    categories = categories_data(db)
    ids = [config.hero_product_id, *config.spotlight_ids, *config.featured_ids]
    rows = execute(db, product_query().where(Product.id.in_(ids))).all()
    items = {item["id"]: item for item in serialize_products(db, rows)}
    if config.hero_product_id not in items:
        return default_home_data(db)
    return {
        "hero": items[config.hero_product_id],
        "spotlights": [items[i] for i in config.spotlight_ids if i in items],
        "featured": [items[i] for i in config.featured_ids if i in items],
        "categories": categories,
        "total": sum(c["count"] for c in categories),
    }


@router.get("/home")
def home(db: Session = Depends(get_db)):
    config = execute(
        db, select(HomepageConfig).where(HomepageConfig.id == 1)
    ).scalar_one_or_none()
    return configured_home_data(db, config) if config else default_home_data(db)


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
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


@router.get("/media/{asset_id}")
def media(asset_id: int, db: Session = Depends(get_db)):
    asset = execute(
        db, select(MediaAsset).where(MediaAsset.id == asset_id)
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(404, "图片不存在")
    path = (MATERIALS_ROOT / asset.storage_key).resolve()
    if not path.is_relative_to(MATERIALS_ROOT) or not path.is_file():
        raise HTTPException(404, "图片文件不存在")
    return FileResponse(path, media_type=asset.content_type)
