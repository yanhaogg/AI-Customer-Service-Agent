"""One request owns one budget, shared by the manager and every specialist invocation."""
from dataclasses import dataclass,field
from time import monotonic
from .config import AgentUnavailableError


@dataclass
class RunBudget:
    settings:object
    deadline:float
    model_calls:int=0
    tool_calls:int=0
    delegations:int=0
    limited:bool=False
    trace:list=field(default_factory=list)

    def remaining(self):return self.deadline-monotonic()

    def model(self):
        if self.remaining()<=0:raise AgentUnavailableError('本轮查询用时较长，请缩小问题后重试。')
        if self.model_calls>=self.settings.max_steps:
            self.limited=True;return False
        self.model_calls+=1
        return True

    def tool(self):
        if self.remaining()<=0:raise AgentUnavailableError('本轮查询用时较长，请缩小问题后重试。')
        if self.tool_calls>=self.settings.max_tools:
            self.limited=True;return False
        self.tool_calls+=1
        return True
