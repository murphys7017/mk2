"""
LLM 抽象接口与通用类型
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, List, Dict, Any


Message = Dict[str, str]


class LLMClient(Protocol):
    """统一 LLM 客户端协议"""

    def call(self, messages: List[Message], *, model: str, params: Dict[str, Any]) -> str:
        """调用 LLM 返回文本"""
        ...


@dataclass
class ProviderSettings:
    name: str
    api_base: str | None = None
    api_key: str | None = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelSettings:
    name: str
    params: Dict[str, Any] = field(default_factory=dict)
