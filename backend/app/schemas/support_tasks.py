"""请求数据结构与输入校验；接口处理逻辑见同名 api 模块。"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["claim", "release", "resolve", "dismiss", "note"]
    note: str = Field(default="", max_length=2000)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value):
        return value.strip()


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(gt=0, strict=True)


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")
