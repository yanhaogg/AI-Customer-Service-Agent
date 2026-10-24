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


# 商品分类表：以 parent_id 自关联支持父子分类。
class CatalogCategory(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "categories"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 唯一的业务分类编码，例如 05_audio，公开接口按该编码筛选。
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # 分类展示名称。
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # 上级分类主键，指向本表；顶级分类为空。 外键：categories.id。 数据库允许 NULL。
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=True
    )


# 商品资料表：保存展示信息、参数及导入质量信息；销售价格和库存另存 SaleOffer。
class Product(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "products"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 商品唯一导入标识，用于导入去重；后台手工商品使用 admin: 加随机标识。
    import_key: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    # 所属分类主键。 外键：categories.id。
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=False, index=True
    )
    # 来源中的原始商品名，也用作缺少中文名时的展示回退。
    name_original: Mapped[str] = mapped_column(Text, nullable=False)
    # 中文商品名；允许为空，展示时优先使用。 数据库允许 NULL。
    name_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 商品品牌，可为空；支持检索。 数据库允许 NULL。
    brand: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    # 商品型号，可为空；支持检索。 数据库允许 NULL。
    model: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    # 来源中的原始商品描述文本。
    description_original: Mapped[str] = mapped_column(Text, nullable=False)
    # 中文商品介绍，用于公开详情与搜索。
    introduction_zh: Mapped[str] = mapped_column(Text, nullable=False)
    # 商品参数 JSON；verified 保存确认参数，其他键可保留导入/提取证据，后台只替换 verified。
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # 导入数据的质量检查/完整性等元信息 JSON；具体键由导入材料提供，不是退款原因 quality。
    quality: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # 商品资料状态；默认 draft，当前公开查询允许 draft/reviewed/published，deleted 表示逻辑删除；能否下单还取决于 SaleOffer。
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 最近更新时间；模型仅提供初始默认值，后续更新由业务代码维护。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 图片文件资源表：保存文件路径、内容哈希和尺寸，可被多条商品图片关联复用。
class MediaAsset(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "media_assets"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        CheckConstraint(
            "width > 0 AND height > 0 AND byte_size > 0", name="ck_media_dimensions"
        ),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 相对素材根目录的文件存储键，用于定位磁盘文件，不是可直接访问的公网 URL。
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    # 文件内容的 SHA-256 十六进制摘要，唯一；用于复用相同图片，避免重复存资源。
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 图片宽度，单位像素，必须大于 0。
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    # 图片高度，单位像素，必须大于 0。
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    # 图片文件大小，单位字节，必须大于 0。
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 文件 MIME 类型，例如 image/jpeg，供文件响应设置内容类型。
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 商品来源表：保留导入来源、原始记录、许可和追溯地址。
class ProductSource(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "product_sources"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint("source_name", "source_sku", name="uq_source_name_sku"),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商品主键。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    # 来源系统/数据集名称；后台编辑生成的来源名为 admin。
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    # 来源中的商品标识；与 source_name 联合唯一，不是商城订单号。
    source_sku: Mapped[str] = mapped_column(Text, nullable=False)
    # 来源商品页面地址，可为空。 数据库允许 NULL。
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 原始官方数据集地址，用于追溯，可为空。 数据库允许 NULL。
    official_dataset_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 元数据镜像地址，用于追溯，可为空。 数据库允许 NULL。
    metadata_mirror_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 来源目录/数据集标注的日期文本；不是数据库采集时间，允许保留原始日期格式。 数据库允许 NULL。
    catalog_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 来源元数据的许可说明；不代表商品图片一定具有相同许可。 数据库允许 NULL。
    metadata_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 本条来源或价格记录的采集时间；与来源声明的价格观察时间可能不同。
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 来源原始记录 JSON，用于保留导入证据和追溯字段。
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


# 商品图片关联表：连接商品、来源与实际图片资源，并记录排序、主图及版权信息。
class ProductImage(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "product_images"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint(
            "product_id", "source_id", "asset_id", name="uq_product_source_asset"
        ),
        CheckConstraint("sort_order >= 0", name="ck_image_sort_order"),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商品主键。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    # 关联的商品来源记录主键，用于追溯图片或参考价格从何而来。 外键：product_sources.id。
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_sources.id"), nullable=False, index=True
    )
    # 实际图片资源主键，指向 MediaAsset；本表只保存关联和来源信息。 外键：media_assets.id。
    asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media_assets.id"), nullable=False
    )
    # 图片排序序号，越小越靠前，必须非负；查询时通常先排主图再排此字段。
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # 是否为商品主图；部分唯一索引保证同商品最多一条 True。
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # 图片替代描述，供展示和无障碍阅读，可为空。 数据库允许 NULL。
    alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 来源记录提供的原始图片地址，可为空。 数据库允许 NULL。
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 图片下载时解析后的地址，用于保留追溯信息，可为空。 数据库允许 NULL。
    resolved_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 图片版权/使用权说明或状态；后台提供的图片写 admin_provided，不等于许可已自动核验。
    rights_status: Mapped[str] = mapped_column(Text, nullable=False)
    # 图片下载时间；未知或不适用时为空。 数据库允许 NULL。
    downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 来源图片的原始元信息 JSON，保留导入证据。
    original_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


Index(
    "uq_product_primary_image",
    ProductImage.product_id,
    unique=True,
    postgresql_where=ProductImage.is_primary.is_(True),
)


# 商品参考价格历史表：保留不同来源/时间的价格，不等于当前可下单的销售报价。
class ProductPriceRecord(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "product_price_records"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint("source_id", "record_key", name="uq_price_source_record"),
        CheckConstraint("amount >= 0", name="ck_price_nonnegative"),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商品主键。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, index=True
    )
    # 关联的商品来源记录主键，用于追溯图片或参考价格从何而来。 外键：product_sources.id。
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_sources.id"), nullable=False
    )
    # 来源内的价格记录标识，与 source_id 联合唯一，避免重复导入同一记录。
    record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # 本次参考价格金额，Decimal，保留两位小数且非负；不是 SaleOffer.price 的成交价。
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 三字符币种代码，例如 USD；金额应结合该字段解释。
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # 参考价格类型，例如 historical_dataset_price 历史数据集价格、admin_reference_price 管理员参考价。
    price_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    # 来源声称观察到该价格的时间；未知时为空，与系统采集时间 collected_at 区分。 数据库允许 NULL。
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 本条来源或价格记录的采集时间；与来源声明的价格观察时间可能不同。
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 是否已经核实为当前价格；默认 False，保留价格记录不意味着实时售价已验证。
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
