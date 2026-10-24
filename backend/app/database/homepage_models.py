"""Singleton homepage selection; all editing is guarded by the super-admin dependency."""

from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database.database import Base
from app.database import models, catalog_models  # Register referenced tables.


# 首页选品配置表：固定 id=1 的单条配置，包含选品顺序、版本和修改人。
class HomepageConfig(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "homepage_config"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (CheckConstraint("id = 1", name="ck_homepage_singleton"),)
    # 固定为 1 的主键；检查约束保证表中最多存在这一条首页配置。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    # 首页主视觉商品主键，由数据库外键关联商品。 外键：products.id。
    hero_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    # 焦点商品主键的有序 JSON 数组；顺序即展示顺序，元素有效性由服务校验，没有逐元素外键。
    spotlight_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    # 精选商品主键的有序 JSON 数组；顺序即展示顺序，元素有效性由服务校验，没有逐元素外键。
    featured_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    # 配置版本号；保存时比较旧版本并递增，防止多个页面互相覆盖。
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 最近修改首页配置的用户主键，通常为超级管理员。 外键：users.id。
    updated_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 最近更新时间；模型仅提供初始默认值，后续更新由业务代码维护。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
