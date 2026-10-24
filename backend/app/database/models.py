from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime
from .database import Base

from datetime import datetime, timezone


# 用户账号表：保存登录身份、密码哈希及权限角色。
class User(Base):

    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "users"

    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    # 登录用户名，要求唯一并建索引；当前表结构允许为空，注册流程会校验输入。 数据库允许 NULL。
    username: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )

    # 权限角色：user 普通用户、super_admin 超级管理员；鉴权时读取数据库当前值，默认 user。
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user"
    )

    # bcrypt 密码哈希字符串，含盐和计算成本；不保存明文密码，表结构允许为空。 数据库允许 NULL。
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    # 用户创建时间；默认使用当前 UTC 时间，但本列 DateTime 未声明 timezone=True。 数据库允许 NULL。
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=True
    )


# LEGACY: 旧 orders 表，仅保留兼容；当前商城订单使用 shop_models.ShopOrder。
# 旧版演示订单表：保留兼容；当前商城交易使用 ShopOrder，不使用此表。
class Order(Base):

    # 数据库中的实际表名；Python 类名与表名通过此属性对应。
    __tablename__ = "orders"

    # 本记录的唯一标识（主键）。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    # 旧版订单的用户编号；仅为整数列，没有声明数据库外键。 数据库允许 NULL。
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 旧版订单的商品名称，允许为空。 数据库允许 NULL。
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # 旧版订单金额，使用浮点数保存；当前商城金额改用 Decimal/Numeric。 数据库允许 NULL。
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 旧版订单状态文本；此模型没有枚举或检查约束，不应套用 ShopOrder 状态机。 数据库允许 NULL。
    status: Mapped[str | None] = mapped_column(String, nullable=True)
