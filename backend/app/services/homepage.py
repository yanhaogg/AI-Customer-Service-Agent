"""公开首页的默认选品与管理员配置展示。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

import logging
from sqlalchemy import case, select
from app.database.catalog_models import CatalogCategory, Product
from app.database.homepage_models import HomepageConfig
from app.services.catalog_queries import (
    execute,
    categories_data,
    serialize_products,
    product_query,
)

logger = logging.getLogger(__name__)


def default_home_data(db):
    """没有有效人工配置时，按固定规则生成默认首页选品。

    输入：
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：hero、spotlights、featured、categories、total；无商品时返回空结构。

    流程：
        1. 统计分类
        2. 优先音响品牌选择主视觉，缺失时取首款
        3. 按手机/电脑及其他分类选取不重复商品
        4. 序列化；不提交。
    """
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
    """根据管理员配置生成首页展示数据。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        config: HomepageConfig ORM 对象；允许 None 的入口会使用默认配置。

    输出：
        dict：hero、spotlights、featured、categories、total。

    流程：
        1. 批量读取配置中的可见商品
        2. 主视觉不可见时退回默认首页
        3. 按配置顺序组装其他仍可见的商品
        4. 附加分类计数；不提交。
    """
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


def home(db):
    """提供公开首页数据入口。

    输入：
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：首页主视觉、焦点商品、精选商品、分类和总数。

    流程：
        1. 查询 id=1 的 HomepageConfig
        2. 有配置调用 configured_home_data，否则调用 default_home_data；不提交。
    """
    config = execute(
        db, select(HomepageConfig).where(HomepageConfig.id == 1)
    ).scalar_one_or_none()
    return configured_home_data(db, config) if config else default_home_data(db)
