"""后台商品资料增删改查与逻辑删除。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from app.storage import VISIBLE_STATUSES
from app.services.catalog_queries import serialize_products
from app.database.catalog_models import (
    CatalogCategory,
    MediaAsset,
    Product,
    ProductImage,
    ProductPriceRecord,
    ProductSource,
)
from app.database.homepage_models import HomepageConfig


def editable_product(db, product_id, lock=False):
    query = select(Product).where(Product.id == product_id, Product.status != "deleted")
    if lock:
        query = query.with_for_update()
    product = db.scalar(query)
    if product is None:
        raise HTTPException(404, "商品不存在或已删除")
    return product


def product_data(db, product):
    category = db.get(CatalogCategory, product.category_id)
    result = serialize_products(db, [(product, category)])[0]
    result.update(
        category_id=product.category_id,
        name_zh=product.name_zh or "",
        description_original=product.description_original,
        introduction_zh=product.introduction_zh,
        specs=(product.specs or {}).get("verified", {}),
        updated_at=product.updated_at,
        image_asset_id=db.scalar(
            select(ProductImage.asset_id)
            .where(ProductImage.product_id == product.id)
            .order_by(
                ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id
            )
            .limit(1)
        ),
    )
    return result


def categories(db):
    return {
        "items": [
            {"id": row.id, "name": row.name, "code": row.code}
            for row in db.scalars(
                select(CatalogCategory).order_by(CatalogCategory.code)
            )
        ]
    }


def products(q, category_id, page, page_size, db):
    query = (
        select(Product, CatalogCategory)
        .join(CatalogCategory, Product.category_id == CatalogCategory.id)
        .where(Product.status != "deleted")
    )
    if category_id:
        query = query.where(Product.category_id == category_id)
    if q.strip():
        query = query.where(
            or_(
                *[
                    column.icontains(q.strip(), autoescape=True)
                    for column in (
                        Product.name_original,
                        Product.name_zh,
                        Product.brand,
                        Product.model,
                    )
                ]
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(Product.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": serialize_products(db, rows),
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


def detail(product_id, db):
    return product_data(db, editable_product(db, product_id))


def apply_changes(db, product, body):
    if db.get(CatalogCategory, body.category_id) is None:
        raise HTTPException(422, "分类不存在")
    if (
        body.image_asset_id is not None
        and db.get(MediaAsset, body.image_asset_id) is None
    ):
        raise HTTPException(422, "图片不存在，请重新上传或选择")
    for field in (
        "category_id",
        "name_original",
        "name_zh",
        "brand",
        "model",
        "description_original",
        "introduction_zh",
    ):
        setattr(product, field, getattr(body, field))
    # Preserve imported source/extracted evidence; administrators edit verified parameters only.
    product.specs = {**(product.specs or {}), "verified": body.specs}
    product.updated_at = datetime.now(timezone.utc)
    db.flush()
    source = db.scalar(
        select(ProductSource).where(
            ProductSource.product_id == product.id, ProductSource.source_name == "admin"
        )
    )
    if source is None:
        source = ProductSource(
            product_id=product.id,
            source_name="admin",
            source_sku=product.import_key,
            collected_at=datetime.now(timezone.utc),
            raw_data={},
        )
        db.add(source)
        db.flush()
    current_image = db.scalar(
        select(ProductImage)
        .where(ProductImage.product_id == product.id)
        .order_by(
            ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id
        )
        .limit(1)
    )
    if (current_image.asset_id if current_image else None) != body.image_asset_id:
        # Historical image rows are retained; only the primary flag is changed.
        for image in db.scalars(
            select(ProductImage).where(
                ProductImage.product_id == product.id, ProductImage.is_primary.is_(True)
            )
        ):
            image.is_primary = False
        db.flush()
        if body.image_asset_id is not None:
            image = db.scalar(
                select(ProductImage).where(
                    ProductImage.product_id == product.id,
                    ProductImage.source_id == source.id,
                    ProductImage.asset_id == body.image_asset_id,
                )
            )
            if image is None:
                image = ProductImage(
                    product_id=product.id,
                    source_id=source.id,
                    asset_id=body.image_asset_id,
                    sort_order=0,
                    rights_status="admin_provided",
                    original_metadata={},
                )
                db.add(image)
            image.is_primary = True
            image.alt = product.name_zh or product.name_original
        else:
            # Removing an image explicitly removes product associations, never shared assets/files.
            from sqlalchemy import delete

            db.execute(
                delete(ProductImage).where(ProductImage.product_id == product.id)
            )
    latest = db.scalar(
        select(ProductPriceRecord)
        .where(ProductPriceRecord.product_id == product.id)
        .order_by(ProductPriceRecord.collected_at.desc(), ProductPriceRecord.id.desc())
        .limit(1)
    )
    if body.price_amount is None:
        if latest is not None:
            raise HTTPException(
                422, "已有参考价格不可清空，请填写新价格；历史价格记录将保留"
            )
    elif (
        latest is None
        or latest.amount != body.price_amount
        or latest.currency != body.price_currency
    ):
        db.add(
            ProductPriceRecord(
                product_id=product.id,
                source_id=source.id,
                record_key=uuid4().hex,
                amount=body.price_amount,
                currency=body.price_currency,
                price_kind="admin_reference_price",
                collected_at=datetime.now(timezone.utc),
                current_price_verified=False,
            )
        )


def create(body, db):
    try:
        product = Product(import_key="admin:" + uuid4().hex, status="published")
        db.add(product)
        # Assign required fields before the first flush.
        with db.no_autoflush:
            apply_changes(db, product, body)
        db.flush()
        result = product_data(db, product)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def update(product_id, body, db):
    try:
        product = editable_product(db, product_id, lock=True)
        if body.updated_at is None or body.updated_at != product.updated_at:
            raise HTTPException(409, "商品已被其他页面修改，请重新加载后编辑")
        apply_changes(db, product, body)
        db.flush()
        result = product_data(db, product)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def remove(product_id, db):
    try:
        # Same lock order as homepage writes avoids a stale config resurrecting deleted selections.
        db.execute(text("SELECT pg_advisory_xact_lock(734120402)"))
        product = editable_product(db, product_id, lock=True)
        config = db.get(HomepageConfig, 1)
        if config and product_id in [
            config.hero_product_id,
            *config.spotlight_ids,
            *config.featured_ids,
        ]:
            config.spotlight_ids = [i for i in config.spotlight_ids if i != product_id]
            config.featured_ids = [i for i in config.featured_ids if i != product_id]
            if config.hero_product_id == product_id:
                replacement = db.scalar(
                    select(Product.id)
                    .where(
                        Product.id != product_id, Product.status.in_(VISIBLE_STATUSES)
                    )
                    .order_by(Product.id)
                    .limit(1)
                )
                if replacement is None:
                    db.delete(config)
                else:
                    config.hero_product_id = replacement
                    config.spotlight_ids = [
                        i for i in config.spotlight_ids if i != replacement
                    ]
                    config.featured_ids = [
                        i for i in config.featured_ids if i != replacement
                    ]
            config.revision += 1
            config.updated_at = datetime.now(timezone.utc)
        product.status = "deleted"
        product.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise
