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
    """提供公开商品分类及可见商品数量。

    输入：
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items 为含 code、name、count 的分类列表。

    流程：
        1. 委托 categories_data 聚合可见商品分类
        2. 包装为 items；不提交。
    """
    return {"items": categories_data(db)}


def products(category, q, sort, page, page_size, db):
    """按分类、关键词和排序分页查询公开商品。

    输入：
        category: str 或 None，公开分类编码；空值表示不限。
        q: str，搜索关键词，可为空。
        sort: str，recommended、price_asc 或 price_desc。
        page: int，从 1 开始的页码（由路由校验）。
        page_size: int，每页条数（由路由校验）。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：items、total、page、page_size、total_pages。

    流程：
        1. 构建可见商品查询
        2. 加分类和转义关键词过滤
        3. 统计总数
        4. 按推荐主键或最新参考价格排序
        5. 分页查询并序列化；不提交。
    """
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
    """查询公开商品详情及同类推荐。

    输入：
        product_id: int，商品主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：商品摘要，加 description_original、specs、quality、related。

    流程：
        1. 查询可见商品（无结果 404）→ 序列化并补全文本与参数
        2. 查询同类其他商品最多 4 款
        3. 合并返回；不提交。
    """
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
    """为公开商品图片解析安全的文件路径。

    输入：
        asset_id: int，媒体资源主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        tuple：(Path 文件路径, str MIME 类型)，由 API 层构造文件响应。

    流程：
        1. 查 MediaAsset（不存在 404）→ 在 MATERIALS_ROOT 下解析路径
        2. 校验未越界且文件存在
        3. 返回路径和 content_type；不提交。
    """
    asset = execute(
        db, select(MediaAsset).where(MediaAsset.id == asset_id)
    ).scalar_one_or_none()
    if not asset:
        raise HTTPException(404, "图片不存在")
    path = (MATERIALS_ROOT / asset.storage_key).resolve()
    if not path.is_relative_to(MATERIALS_ROOT) or not path.is_file():
        raise HTTPException(404, "图片文件不存在")
    return path, asset.content_type
