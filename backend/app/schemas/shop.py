"""请求数据结构与输入校验；接口处理逻辑见同名 api 模块。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

PositiveId = Annotated[StrictInt, Field(gt=0)]

Quantity = Annotated[StrictInt, Field(ge=1, le=99)]

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddressBody(StrictBody):
    recipient: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=6, max_length=30, pattern=r"^\+?[0-9 ()-]+$")
    region: str = Field(min_length=2, max_length=200)
    detail: str = Field(min_length=3, max_length=500)
    postal_code: str = Field(default="", max_length=20)
    is_default: bool = False

    @field_validator("recipient", "phone", "region", "detail")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("必填信息不能为空")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def phone_digits(cls, value):
        if not 6 <= sum(char.isdigit() for char in value) <= 20:
            raise ValueError("请输入有效联系电话")
        return value


class CartAdd(StrictBody):
    product_id: PositiveId
    quantity: Quantity = 1


class CartUpdate(StrictBody):
    quantity: Quantity


class Selection(StrictBody):
    product_id: PositiveId
    quantity: Quantity


class PricedSelection(Selection):
    expected_price: Money
    currency: str = Field(pattern="^(USD|CNY|EUR|GBP|JPY|HKD)$")


class PreviewBody(StrictBody):
    items: list[Selection] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique(self):
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError("商品不能重复")
        return self


class CheckoutBody(PreviewBody):
    items: list[PricedSelection] = Field(min_length=1, max_length=50)
    address_id: PositiveId
    cart_item_ids: list[PositiveId] = Field(default_factory=list, max_length=50)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    note: str = Field(default="", max_length=500)


class OfferBody(StrictBody):
    price: Money
    currency: str = Field(pattern="^(USD|CNY|EUR|GBP|JPY|HKD)$")
    stock: Annotated[StrictInt, Field(ge=0, le=1000000)]
    is_active: bool
    updated_at: datetime | None = None


class ShippingBody(StrictBody):
    carrier: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(
        min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9-]+$"
    )
