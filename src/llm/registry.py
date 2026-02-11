"""
LLM Provider 注册表
"""
from __future__ import annotations

from typing import Callable, Dict

from .base import LLMClient, ProviderSettings
from .providers import OllamaProvider, BailianOpenAIProvider


ProviderFactory = Callable[[ProviderSettings], LLMClient]


PROVIDERS: Dict[str, ProviderFactory] = {
    "ollama": OllamaProvider,
    "bailian": BailianOpenAIProvider,
}


def create_provider(name: str, settings: ProviderSettings) -> LLMClient:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {name}")
    return PROVIDERS[name](settings)
