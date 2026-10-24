"""Transactional shopping data; legacy demonstration orders are deliberately preserved."""

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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base
from . import models, catalog_models  # Register FK targets.


# 演示销售配置表：每款商品一条，独立维护成交售价、可售库存和上架标记。
class SaleOffer(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "sale_offers"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        CheckConstraint("stock >= 0 AND price > 0", name="ck_offer_stock_price"),
    )
    # 商品主键同时作为本表主键，使每款商品最多有一条销售配置。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), primary_key=True, nullable=False
    )
    # 当前演示销售单价，Decimal，保留两位小数且必须大于 0；用于下单计价。
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 三字符币种代码，例如 USD；金额应结合该字段解释。
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # 当前可售件数，必须非负；下单时预扣，取消/超时或符合条件的退款时回补。
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 销售上架开关，默认 False；有商品资料不代表允许下单，还需此标记及足够库存。
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 销售配置最近修改时间；更新售价/库存时维护，也用于识别后台编辑冲突。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# 购物车条目表：记录某用户购买某商品的意向数量，同用户同商品只保留一条。
class CartItem(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "cart_items"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_cart_quantity"),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # 关联的商品主键。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    # 该商品的件数，数据库约束为 1～99。
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


# 用户收货地址表：保存可编辑地址；下单时会另存快照，不直接修改历史订单。
class ShippingAddress(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "shipping_addresses"
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # 收件人姓名。
    recipient: Mapped[str] = mapped_column(String(80), nullable=False)
    # 收件人联系电话，保存为字符串以保留格式。
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    # 省市区等区域信息。
    region: Mapped[str] = mapped_column(String(200), nullable=False)
    # 街道、门牌等详细地址，和 region 一起构成完整地址。
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    # 邮政编码；未填写时默认为空字符串。
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    # 是否为用户默认地址，默认 False；默认唯一性由地址服务在用户锁内维护。
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# 商城订单主表：记录交易状态、总额、地址快照、物流及重试去重信息。
class ShopOrder(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "shop_orders"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_order_user_request"),
        CheckConstraint("total > 0", name="ck_shop_order_total"),
        CheckConstraint(
            "status IN ('pending_payment','paid','shipped','completed','cancelled','refunded')",
            name="ck_shop_order_status",
        ),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 面向用户的唯一订单编号；不同于数据库 id。
    number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    # 所属用户的主键，用于归属检查和按用户隔离数据。 外键：users.id。
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # 客户端生成的幂等请求标识，用于识别网络重试、防止重复处理。
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # 请求内容的 SHA-256 指纹；检测同一 request_key 是否被用于不同内容。
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 订单状态：pending_payment 待支付、paid 已支付、shipped 已发货、completed 已完成、cancelled 已取消、refunded 已退款。
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_payment", index=True
    )
    # 下单时确定的订单总金额，Decimal，保留两位小数且必须大于 0。
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # 三字符币种代码，例如 USD；金额应结合该字段解释。
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # 下单时收货人、电话、区域等地址信息的 JSON 快照；后续编辑地址簿不改变此值。
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # 用户下单备注，默认空字符串。
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 本记录创建时间；未显式提供时由数据库生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 待支付截止时间；当前下单服务设为创建后 30 分钟，用于按需取消并回收库存。
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # 演示支付完成时间；未支付时为空。 数据库允许 NULL。
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 整单模拟退款完成时间；未退款时为空。 数据库允许 NULL。
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 管理员登记发货时间；未发货时为空。 数据库允许 NULL。
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 用户确认收货、订单完成的时间；未完成时为空。 数据库允许 NULL。
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 用户取消或支付超时取消的时间；未取消时为空。 数据库允许 NULL。
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 订单取消原因，例如用户取消或超时未支付；未取消时通常为空。 数据库允许 NULL。
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 发货快递公司名称；尚未登记物流时为空。 数据库允许 NULL。
    carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 发货快递单号；不是订单编号，尚未登记物流时为空。 数据库允许 NULL。
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)


# 订单商品明细表：一张订单可有多条，保存下单时的商品名、图片和成交单价快照。
class ShopOrderItem(Base):
    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "shop_order_items"
    # 表级唯一约束、检查约束及索引；用于保证业务数据有效并支持查询。
    __table_args__ = (
        CheckConstraint(
            "quantity BETWEEN 1 AND 99 AND unit_price > 0", name="ck_order_item_values"
        ),
    )
    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, nullable=False
    )
    # 关联的商城订单主键。 外键：shop_orders.id。
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_orders.id"), nullable=False, index=True
    )
    # 关联的商品主键。 外键：products.id。
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    # 下单时商品名称快照；商品改名不改变历史订单中的此字段。
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # 下单时选定的商品图片资源主键；无图时为空，不跟随商品换主图而变化。 外键：media_assets.id。 数据库允许 NULL。
    image_asset_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media_assets.id"), nullable=True
    )
    # 下单成交单价快照，Decimal，保留两位小数且大于 0；小计为此值乘 quantity。
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 该商品的件数，数据库约束为 1～99。
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


SHOP_TABLES = [
    model.__table__
    for model in (SaleOffer, CartItem, ShippingAddress, ShopOrder, ShopOrderItem)
]
