"""admin 接口的请求字段与输入校验。"""

from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

PositiveId = Annotated[StrictInt, Field(gt=0)]


class HomepageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hero_product_id: PositiveId
    spotlight_ids: list[PositiveId] = Field(max_length=2)
    featured_ids: list[PositiveId] = Field(max_length=8)
    revision: Annotated[StrictInt, Field(ge=0)]

    @model_validator(mode="after")
    def unique_products(self):
        ids = [self.hero_product_id, *self.spotlight_ids, *self.featured_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("首页各区域不能重复选择同一商品")
        return self
