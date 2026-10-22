"""首页选品配置维护，使用版本号和数据库锁防止覆盖。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, text
from app.database.homepage_models import HomepageConfig
from app.database.catalog_models import Product
from app.services.homepage import default_home_data, configured_home_data
from app.services.catalog_queries import product_query


def config_response(db, config):
    preview = configured_home_data(db, config) if config else default_home_data(db)
    return {
        "revision": config.revision if config else 0,
        "hero_product_id": (
            config.hero_product_id
            if config
            else preview["hero"]["id"] if preview["hero"] else None
        ),
        "spotlight_ids": (
            config.spotlight_ids
            if config
            else [item["id"] for item in preview["spotlights"]]
        ),
        "featured_ids": (
            config.featured_ids
            if config
            else [item["id"] for item in preview["featured"]]
        ),
        "preview": preview,
    }


def get_homepage(db):
    return config_response(db, db.get(HomepageConfig, 1))


def save_homepage(body, db, user):
    try:
        db.execute(text("SET LOCAL lock_timeout = '15s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(734120402)"))
        config = db.scalar(
            select(HomepageConfig).where(HomepageConfig.id == 1).with_for_update()
        )
        current_revision = config.revision if config else 0
        if body.revision != current_revision:
            raise HTTPException(409, "首页配置已被修改，请重新加载后再保存")
        ids = [body.hero_product_id, *body.spotlight_ids, *body.featured_ids]
        available = db.execute(
            product_query().where(Product.id.in_(ids)).with_for_update(read=True)
        ).all()
        missing = set(ids) - {row[0].id for row in available}
        if missing:
            raise HTTPException(422, "部分商品不存在或不可展示，请重新选择")
        if config is None:
            config = HomepageConfig(id=1)
            db.add(config)
        config.hero_product_id = body.hero_product_id
        config.spotlight_ids = body.spotlight_ids
        config.featured_ids = body.featured_ids
        config.revision = current_revision + 1
        config.updated_by = user.id
        config.updated_at = datetime.now(timezone.utc)
        db.flush()
        result = config_response(db, config)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
