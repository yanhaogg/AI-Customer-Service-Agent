"""PostgreSQL product catalog tables, separate from users and orders."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base


class CatalogCategory(Base):
    __tablename__ = "categories"
    id = Column(BigInteger, Identity(), primary_key=True)
    code = Column(String(100), nullable=False, unique=True)
    name = Column(Text, nullable=False)
    parent_id = Column(BigInteger, ForeignKey("categories.id"), nullable=True)


class Product(Base):
    __tablename__ = "products"
    id = Column(BigInteger, Identity(), primary_key=True)
    import_key = Column(String(150), nullable=False, unique=True)
    category_id = Column(
        BigInteger, ForeignKey("categories.id"), nullable=False, index=True
    )
    name_original = Column(Text, nullable=False)
    name_zh = Column(Text, nullable=True)
    brand = Column(Text, index=True)
    model = Column(Text, index=True)
    description_original = Column(Text, nullable=False)
    introduction_zh = Column(Text, nullable=False)
    specs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    quality = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status = Column(String(20), nullable=False, server_default="draft")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "width > 0 AND height > 0 AND byte_size > 0", name="ck_media_dimensions"
        ),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    storage_key = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    content_type = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductSource(Base):
    __tablename__ = "product_sources"
    __table_args__ = (
        UniqueConstraint("source_name", "source_sku", name="uq_source_name_sku"),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    product_id = Column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    source_name = Column(Text, nullable=False)
    source_sku = Column(Text, nullable=False)
    product_url = Column(Text)
    official_dataset_url = Column(Text)
    metadata_mirror_url = Column(Text)
    catalog_date = Column(Text)
    metadata_license = Column(Text)
    collected_at = Column(DateTime(timezone=True), nullable=False)
    raw_data = Column(JSONB, nullable=False)


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "source_id", "asset_id", name="uq_product_source_asset"
        ),
        CheckConstraint("sort_order >= 0", name="ck_image_sort_order"),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    product_id = Column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    source_id = Column(
        BigInteger, ForeignKey("product_sources.id"), nullable=False, index=True
    )
    asset_id = Column(BigInteger, ForeignKey("media_assets.id"), nullable=False)
    sort_order = Column(Integer, nullable=False)
    is_primary = Column(Boolean, nullable=False, server_default=text("false"))
    alt = Column(Text)
    source_url = Column(Text)
    resolved_url = Column(Text)
    rights_status = Column(Text, nullable=False)
    downloaded_at = Column(DateTime(timezone=True))
    original_metadata = Column(JSONB, nullable=False)


Index(
    "uq_product_primary_image",
    ProductImage.product_id,
    unique=True,
    postgresql_where=ProductImage.is_primary.is_(True),
)


class ProductPriceRecord(Base):
    __tablename__ = "product_price_records"
    __table_args__ = (
        UniqueConstraint("source_id", "record_key", name="uq_price_source_record"),
        CheckConstraint("amount >= 0", name="ck_price_nonnegative"),
    )
    id = Column(BigInteger, Identity(), primary_key=True)
    product_id = Column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    source_id = Column(BigInteger, ForeignKey("product_sources.id"), nullable=False)
    record_key = Column(String(64), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    price_kind = Column(String(50), nullable=False)
    observed_at = Column(DateTime(timezone=True))
    collected_at = Column(DateTime(timezone=True), nullable=False)
    current_price_verified = Column(
        Boolean, nullable=False, server_default=text("false")
    )


CATALOG_TABLES = [
    model.__table__
    for model in (
        CatalogCategory,
        Product,
        MediaAsset,
        ProductSource,
        ProductImage,
        ProductPriceRecord,
    )
]
