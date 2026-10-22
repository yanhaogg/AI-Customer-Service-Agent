"""human_support 接口的请求字段与输入校验。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=10000)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("content")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("回复不能为空")
        return value.strip()


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
