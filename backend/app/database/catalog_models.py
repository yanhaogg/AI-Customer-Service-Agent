"""PostgreSQL product catalog tables, separate from users and orders."""

from typing import Any

from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=True
    )


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    import_key: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=False, index=True
    )
    name_original: Mapped[str] = mapped_column(Text, nullable=False)
    name_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    description_original: Mapped[str] = mapped_column(Text, nullable=False)
    introduction_zh: Mapped[str] = mapped_column(Text, nullable=False)
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    quality: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "width > 0 AND height > 0 AND byte_size > 0", name="ck_media_dimensions"
        ),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductSource(Base):
    __tablename__ = "product_sources"
    __table_args__ = (
        UniqueConstraint("source_name", "source_sku", name="uq_source_name_sku"),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_sku: Mapped[str] = mapped_column(Text, nullable=False)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_dataset_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_mirror_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalog_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "source_id", "asset_id", name="uq_product_source_asset"
        ),
        CheckConstraint("sort_order >= 0", name="ck_image_sort_order"),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_sources.id"), nullable=False, index=True
    )
    asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media_assets.id"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rights_status: Mapped[str] = mapped_column(Text, nullable=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    original_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


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
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_sources.id"), nullable=False
    )
    record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_price_verified: Mapped[bool] = mapped_column(
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
