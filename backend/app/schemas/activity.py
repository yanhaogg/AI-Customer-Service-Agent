"""activity 接口的请求字段与输入校验。"""

from typing import Annotated
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)

PositiveId = Annotated[StrictInt, Field(gt=0)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(StrictBody):
    title: str = Field(default="新的咨询", min_length=1, max_length=100)
    product_id: PositiveId | None = None
    order_number: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("标题不能为空")
        return value.strip()


class MessageCreate(StrictBody):
    content: str = Field(min_length=1, max_length=10000)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("content")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("消息不能为空")
        return value.strip()


class BrowseCreate(StrictBody):
    product_id: PositiveId
    visit_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class ReadThrough(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read_through: AwareDatetime
