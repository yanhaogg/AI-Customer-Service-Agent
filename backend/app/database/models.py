from sqlalchemy import Column, Integer, String, Float, DateTime
from .database import Base

from datetime import datetime, timezone


class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(String, unique=True, index=True)

    role = Column(String(20), nullable=False, default="user", server_default="user")

    password_hash = Column(String)

    created_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# LEGACY: 旧 orders 表，仅保留兼容；当前商城订单使用 shop_models.ShopOrder。
class Order(Base):

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer)

    product_name = Column(String)

    amount = Column(Float)

    status = Column(String)
