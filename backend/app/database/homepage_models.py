"""Singleton homepage selection; all editing is guarded by the super-admin dependency."""
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database.database import Base
from app.database import models, catalog_models  # Register referenced tables.

class HomepageConfig(Base):
 __tablename__ = 'homepage_config'
 __table_args__ = (CheckConstraint('id = 1', name='ck_homepage_singleton'),)
 id = Column(Integer, primary_key=True)
 hero_product_id = Column(BigInteger, ForeignKey('products.id'), nullable=False)
 spotlight_ids = Column(JSONB, nullable=False)
 featured_ids = Column(JSONB, nullable=False)
 revision = Column(Integer, nullable=False, default=1)
 updated_by = Column(Integer, ForeignKey('users.id'), nullable=False)
 updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
