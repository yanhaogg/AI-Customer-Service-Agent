"""One request owns one budget, shared by the manager and every specialist invocation."""

from dataclasses import dataclass, field
from time import monotonic
from .config import AgentUnavailableError


@dataclass
class RunBudget:
    settings: object
    deadline: float
    model_calls: int = 0
    tool_calls: int = 0
    delegations: int = 0
    limited: bool = False
    trace: list = field(default_factory=list)

    def remaining(self):
        # 使用单调时钟计算剩余时间，避免系统时间调整影响本轮超时判断。
        return self.deadline - monotonic()

    def model(self):
        # Manager 和所有专员共用此计数，避免反复委派后绕过模型总次数上限。
        if self.remaining() <= 0:
            raise AgentUnavailableError("本轮查询用时较长，请缩小问题后重试。")
        if self.model_calls >= self.settings.max_steps:
            self.limited = True
            return False
        self.model_calls += 1
        return True

    def tool(self):
        # 所有专员共用工具总额度；局部子图重建不会重置这个额度。
        if self.remaining() <= 0:
            raise AgentUnavailableError("本轮查询用时较长，请缩小问题后重试。")
        if self.tool_calls >= self.settings.max_tools:
            self.limited = True
            return False
        self.tool_calls += 1
        return True
