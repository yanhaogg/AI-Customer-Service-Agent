"""Singleton homepage selection; all editing is guarded by the super-admin dependency."""

from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database.database import Base
from app.database import models, catalog_models  # Register referenced tables.


class HomepageConfig(Base):
    __tablename__ = "homepage_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_homepage_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    hero_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    spotlight_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    featured_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
