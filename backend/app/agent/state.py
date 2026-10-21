"""Per-request graph state; durable user/assistant history remains in PostgreSQL."""
from typing import Annotated,TypedDict
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict,total=False):
    messages:Annotated[list[AnyMessage],add_messages]
    steps:int
    tool_calls:int
    trace:Annotated[list[dict],operator.add]
    limited:bool


class ManagerState(TypedDict,total=False):
    messages:Annotated[list[AnyMessage],add_messages]
    pending_calls:list[dict]
    active_call:dict|None
    manager_rounds:int
    reports:Annotated[list[dict],operator.add]
    trace:Annotated[list[dict],operator.add]
    delegations:Annotated[list[dict],operator.add]
