"""Transactional shopping data; legacy demonstration orders are deliberately preserved."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Identity, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base
from . import models, catalog_models  # Register FK targets.


class SaleOffer(Base):
    __tablename__ = 'sale_offers'
    __table_args__ = (CheckConstraint('stock >= 0 AND price > 0', name='ck_offer_stock_price'),)
    product_id = Column(BigInteger, ForeignKey('products.id'), primary_key=True)
    price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default='USD')
    stock = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CartItem(Base):
    __tablename__ = 'cart_items'
    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='uq_cart_user_product'),
                      CheckConstraint('quantity BETWEEN 1 AND 99', name='ck_cart_quantity'))
    id = Column(BigInteger, Identity(), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    product_id = Column(BigInteger, ForeignKey('products.id'), nullable=False)
    quantity = Column(Integer, nullable=False)


class ShippingAddress(Base):
    __tablename__ = 'shipping_addresses'
    id = Column(BigInteger, Identity(), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    recipient = Column(String(80), nullable=False)
    phone = Column(String(30), nullable=False)
    region = Column(String(200), nullable=False)
    detail = Column(String(500), nullable=False)
    postal_code = Column(String(20), nullable=False, default='')
    is_default = Column(Boolean, nullable=False, default=False)


class ShopOrder(Base):
    __tablename__ = 'shop_orders'
    __table_args__ = (UniqueConstraint('user_id', 'request_key', name='uq_order_user_request'),
                      CheckConstraint('total > 0', name='ck_shop_order_total'),
                      CheckConstraint("status IN ('pending_payment','paid','shipped','completed','cancelled','refunded')", name='ck_shop_order_status'))
    id = Column(BigInteger, Identity(), primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    request_key = Column(String(64), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(30), nullable=False, default='pending_payment', index=True)
    total = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    shipping_address = Column(JSONB, nullable=False)
    note = Column(Text, nullable=False, default='')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    paid_at = Column(DateTime(timezone=True))
    refunded_at = Column(DateTime(timezone=True))
    shipped_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    cancel_reason = Column(Text)
    carrier = Column(String(100))
    tracking_number = Column(String(100))


class ShopOrderItem(Base):
    __tablename__ = 'shop_order_items'
    __table_args__ = (CheckConstraint('quantity BETWEEN 1 AND 99 AND unit_price > 0', name='ck_order_item_values'),)
    id = Column(BigInteger, Identity(), primary_key=True)
    order_id = Column(BigInteger, ForeignKey('shop_orders.id'), nullable=False, index=True)
    product_id = Column(BigInteger, ForeignKey('products.id'), nullable=False)
    name = Column(Text, nullable=False)
    image_asset_id = Column(BigInteger, ForeignKey('media_assets.id'))
    unit_price = Column(Numeric(12, 2), nullable=False)
    quantity = Column(Integer, nullable=False)


SHOP_TABLES = [model.__table__ for model in (SaleOffer, CartItem, ShippingAddress, ShopOrder, ShopOrderItem)]
