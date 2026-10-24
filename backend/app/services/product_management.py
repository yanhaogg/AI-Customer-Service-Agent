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
    """读取未逻辑删除的后台可编辑商品。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        product_id: int，商品主键。
        lock: bool，是否对查询结果加行锁，默认 False。

    输出：
        Product ORM 对象；不存在或已删除时抛 404。

    流程：
        1. 按主键和非 deleted 状态查询
        2. 按 lock 决定是否加行锁
        3. 返回对象；不提交。
    """
    query = select(Product).where(Product.id == product_id, Product.status != "deleted")
    if lock:
        query = query.with_for_update()
    product = db.scalar(query)
    if product is None:
        raise HTTPException(404, "商品不存在或已删除")
    return product


def product_data(db, product):
    """组装后台商品编辑页需要的数据。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        product: Product ORM 对象。

    输出：
        dict：公开摘要加分类主键、编辑文本、已验证参数、更新时间和主图资源主键。

    流程：
        1. 查询分类
        2. 复用 serialize_products
        3. 补充编辑字段及主图主键；不提交。
    """
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
    """列出后台可选的全部商品分类。

    输入：
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items 列表，每项为 id、name、code。

    流程：
        1. 按 code 排序查询分类
        2. 转为字典；不限制分类内商品数量，不提交。
    """
    return {
        "items": [
            {"id": row.id, "name": row.name, "code": row.code}
            for row in db.scalars(
                select(CatalogCategory).order_by(CatalogCategory.code)
            )
        ]
    }


def products(q, category_id, page, page_size, db):
    """分页检索后台未删除商品。

    输入：
        q: str，搜索关键词，可为空。
        category_id: int 或 None，后台分类主键；空值表示不限。
        page: int，从 1 开始的页码（由路由校验）。
        page_size: int，每页条数（由路由校验）。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items、total、total_pages。

    流程：
        1. 连接商品与分类并排除 deleted
        2. 按分类主键和转义关键词过滤
        3. 计数
        4. 按商品主键倒序分页
        5. 序列化；不提交。
    """
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
    """获取后台单个可编辑商品详情。

    输入：
        product_id: int，商品主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：product_data 组装的编辑信息。

    流程：
        1. editable_product 校验商品
        2. product_data 组装；不提交。
    """
    return product_data(db, editable_product(db, product_id))


def apply_changes(db, product, body):
    """把后台表单应用到商品、主图和参考价格历史。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        product: Product ORM 对象。
        body: ProductWrite：商品资料、分类、verified 参数、主图资源、参考价格及编辑版本时间。

    输出：
        None；修改商品并按需新增来源、图片关联及价格记录。

    流程：
        1. 校验分类/图片资源
        2. 写基础字段与 verified 参数、保留导入证据
        3. flush 并取得 admin 来源
        4. 按主图变化维护关联
        5. 比较最新价格，有变化新增历史记录；不 commit，调用方统一提交。
    """
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
    """创建后台手工录入的商品。

    输入：
        body: ProductWrite：商品资料、分类、verified 参数、主图资源、参考价格及编辑版本时间。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：新商品编辑详情。

    流程：
        1. 生成 admin 导入键并创建 published 商品
        2. 暂停自动 flush 后应用必填字段及关联
        3. flush、组装、提交；异常时回滚。
    """
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
    """更新商品并检测页面数据是否已过期。

    输入：
        product_id: int，商品主键。
        body: ProductWrite：商品资料、分类、verified 参数、主图资源、参考价格及编辑版本时间。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：更新后的商品编辑详情。

    流程：
        1. 锁未删除商品
        2. 比对 body.updated_at（缺失或不匹配返回 409）→ apply_changes
        3. flush、组装、提交；异常回滚。
    """
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
    """逻辑删除商品并清理首页选品引用。

    输入：
        product_id: int，商品主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        None；商品改 deleted，必要时调整或删除首页配置。

    流程：
        1. 先获取与首页写入相同的事务级咨询锁
        2. 锁商品
        3. 移除选品引用，主视觉缺失时选替代商品或删除配置
        4. 更新配置版本及商品时间
        5. 提交；异常回滚，保留商品历史记录。
    """
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
