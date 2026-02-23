"""
统一 LLM 对外接口
"""
from __future__ import annotations

from typing import Dict, Any, List

from .base import LLMClient, Message
from .config import LLMConfig
from .registry import create_provider


class LLMProvider:
    """统一对外接口：provider + model + params"""

    def __init__(
        self,
        provider: str,
        model: str,
        *,
        config: LLMConfig,
        default_params: Dict[str, Any] | None = None,
    ) -> None:
        self._provider_name = provider
        self._model_name = model
        self._config = config

        provider_cfg = config.provider(provider)
        self._client: LLMClient = create_provider(provider, provider_cfg)

        model_cfg = config.model(provider, model)
        self._base_params: Dict[str, Any] = dict(model_cfg.params)
        if default_params:
            self._base_params.update(default_params)

    @classmethod
    def from_config(
        cls,
        provider: str,
        model: str,
        *,
        config_path: str = "config/llm.yaml",
        default_params: Dict[str, Any] | None = None,
    ) -> "LLMProvider":
        config = LLMConfig.load(config_path)
        return cls(provider, model, config=config, default_params=default_params)

    def call(self, messages: List[Message], **params: Any) -> str:
        merged = dict(self._base_params)
        merged.update(params)
        return self._client.call(messages, model=self._model_name, params=merged)
