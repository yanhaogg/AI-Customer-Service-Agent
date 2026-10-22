from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime
from .database import Base

from datetime import datetime, timezone


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    username: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )

    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user"
    )

    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    created_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=True
    )


# LEGACY: 旧 orders 表，仅保留兼容；当前商城订单使用 shop_models.ShopOrder。
class Order(Base):

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product_name: Mapped[str | None] = mapped_column(String, nullable=True)

    amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str | None] = mapped_column(String, nullable=True)
