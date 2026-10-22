"""Per-request graph state; durable user/assistant history remains in PostgreSQL."""

from typing import Annotated, TypedDict
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# 状态只在本轮图执行中流转；持久聊天由 API 写入 PostgreSQL。
# Annotated 的第二项是合并规则：messages 按消息 ID 合并，trace 按列表追加。
class AgentState(TypedDict, total=False):
    # 专员局部状态：messages 是模型上下文，steps/tool_calls 是局部计数。
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int
    tool_calls: int
    trace: Annotated[list[dict], operator.add]
    limited: bool


# pending_calls / active_call 每次更新会替换；reports / trace / delegations 则累积。
# 节点只需返回本次新增消息或报告，不要返回整份旧列表，否则可能重复累积。
class ManagerState(TypedDict, total=False):
    # 主图保存待派发队列、当前任务和专员报告；业务数据库不存放在图状态中。
    messages: Annotated[list[AnyMessage], add_messages]
    pending_calls: list[dict]
    active_call: dict | None
    manager_rounds: int
    reports: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]
    delegations: Annotated[list[dict], operator.add]
