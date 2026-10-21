"""请求数据结构与输入校验；接口处理逻辑见同名 api 模块。"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contact(Body):
    intent: Literal["general", "human"] = "general"


class Reminder(Body):
    note: str = Field(default="请尽快安排发货，并告知预计发货时间。", max_length=500)


class RefundCreate(Body):
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    reason: Literal[
        "not_needed",
        "wrong_order",
        "change_mind",
        "not_received",
        "quality",
        "damaged",
        "payment_issue",
        "other",
    ]
    description: str = Field(min_length=10, max_length=2000)
    contact_phone: str = Field(min_length=6, max_length=30, pattern=r"^\+?[0-9 ()-]+$")
    received: bool
    evidence_ids: list[int] = Field(default_factory=list, max_length=3)

    @field_validator("description")
    @classmethod
    def description_nonblank(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("情况说明至少10字")
        return value.strip()

    @field_validator("contact_phone")
    @classmethod
    def valid_phone(cls, value):
        if not 6 <= sum(c.isdigit() for c in value) <= 20:
            raise ValueError("请输入有效联系电话")
        return value


class EvidenceUpload(Body):
    data: str = Field(max_length=8_000_000)


class Review(Body):
    action: Literal["approve", "reject", "confirm_return"]
    note: str = Field(min_length=5, max_length=1000)
    return_address: str = Field(default="", max_length=1000)

    @field_validator("note")
    @classmethod
    def note_nonblank(cls, value):
        if len(value.strip()) < 5:
            raise ValueError("处理说明至少5字")
        return value.strip()


class ReturnShipping(Body):
    carrier: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(
        min_length=3, max_length=100, pattern=r"^[A-Za-z0-9-]+$"
    )


class HandleReminder(Body):
    note: str = Field(min_length=5, max_length=500)
