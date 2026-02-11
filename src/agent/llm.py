"""
LLM 客户端协议和桩实现
"""
from __future__ import annotations

from typing import Protocol, List, Dict, Any, Optional

from ..llm import LLMGateway


class LLMClient(Protocol):
    """LLM 客户端协议"""
    
    def call(self, messages: List[Dict[str, str]]) -> str:
        """调用 LLM 返回文本"""
        ...


class GatewayLLM:
    """使用统一 LLMGateway 的适配器（保持 call(messages) 形态）"""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        config_path: str = "config/llm.yaml",
        default_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._gateway = LLMGateway.from_config(
            provider=provider,
            model=model,
            config_path=config_path,
            default_params=default_params,
        )

    def call(self, messages: List[Dict[str, str]]) -> str:
        return self._gateway.call(messages)
