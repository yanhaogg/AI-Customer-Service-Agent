"""DeepSeek-compatible chat configuration. Never log or return API keys."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values
from langchain_openai import ChatOpenAI


class AgentConfigurationError(RuntimeError):
    pass


class AgentUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSettings:
    api_key: str = field(repr=False)
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    max_steps: int = 16
    max_tools: int = 24
    max_manager_steps: int = 6
    max_worker_steps: int = 4
    max_delegations: int = 6
    timeout: float = 20
    budget: float = 90


def load_settings():
    values = {
        **dotenv_values(Path(__file__).resolve().parents[2] / ".env"),
        **os.environ,
    }
    # Accept the existing project names; LLM_* overrides allow compatible providers.
    key = (
        values.get("LLM_API_KEY")
        or values.get("DS_API_KEY")
        or values.get("DEEPSEEK_API_KEY")
        or ""
    )
    model = values.get("LLM_MODEL") or values.get("DEEPSEEK") or "deepseek-flash"
    base = (
        values.get("LLM_BASE_URL")
        or values.get("DS_API_BASE")
        or "https://api.deepseek.com"
    )
    parsed = urlparse(base)
    if not key.strip():
        raise AgentConfigurationError(
            "客服模型尚未配置，请管理员在 backend/.env 填写 DS_API_KEY。"
        )
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
    ):
        raise AgentConfigurationError(
            "客服模型接口地址配置无效，请管理员检查 DS_API_BASE。"
        )
    if not model.strip():
        raise AgentConfigurationError("客服模型名称未配置，请管理员检查 DEEPSEEK。")
    return ModelSettings(
        api_key=key.strip(), model=model.strip(), base_url=base.rstrip("/")
    )


def make_model(settings, timeout):
    options = {}
    if (urlparse(settings.base_url).hostname or "").endswith("deepseek.com"):
        # Non-thinking tool calling avoids dropping required reasoning_content between turns.
        options["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=timeout,
        max_retries=0,
        max_tokens=1600,
        **options,
    )
