"""admin_products 接口的请求字段与输入校验。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

PositiveId = Annotated[StrictInt, Field(gt=0)]


class ProductWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: PositiveId
    name_original: str = Field(min_length=1, max_length=500)
    name_zh: str = Field(default="", max_length=500)
    brand: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=200)
    description_original: str = Field(min_length=1, max_length=30000)
    introduction_zh: str = Field(min_length=1, max_length=10000)
    specs: dict[str, str] = Field(default_factory=dict, max_length=100)
    image_asset_id: PositiveId | None = None
    price_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    price_currency: str = Field(default="USD", pattern="^(USD|CNY|EUR|GBP|JPY|HKD)$")
    updated_at: datetime | None = None

    @field_validator("name_original", "description_original", "introduction_zh")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("必填字段不能为空")
        return value.strip()

    @field_validator("specs")
    @classmethod
    def limited_specs(cls, value):
        if any(
            not key.strip() or len(key) > 100 or len(item) > 2000
            for key, item in value.items()
        ):
            raise ValueError("参数名称限 100 字，参数值限 2000 字")
        return value


class ImageUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: str = Field(max_length=8_000_000)
