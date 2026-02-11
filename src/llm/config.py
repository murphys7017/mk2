"""
LLM 配置加载
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from pathlib import Path
from typing import Dict, Any

import yaml
from dotenv import load_dotenv

from .base import ProviderSettings, ModelSettings


_ENV_PLACEHOLDER_RE = re.compile(r"^<([A-Z0-9_]+)>$")


def resolve_env_placeholder(value: str, *, provider_name: str, field_name: str) -> str:
    """
    Resolve <ENV_VAR> placeholder strictly.
    Only matches full string like "<ENV_VAR>".
    """
    match = _ENV_PLACEHOLDER_RE.match(value.strip())
    if not match:
        return value

    env_name = match.group(1)
    env_value = os.getenv(env_name)
    if not env_value:
        raise ValueError(
            f"Environment variable '{env_name}' not set for provider '{provider_name}' field '{field_name}'. "
            f"Please সেট定该环境变量。"
        )
    return env_value


@dataclass
class LLMConfig:
    providers: Dict[str, ProviderSettings] = field(default_factory=dict)
    models: Dict[str, Dict[str, ModelSettings]] = field(default_factory=dict)
    default_provider: str | None = None
    default_models: Dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "LLMConfig":
        # Load .env into environment (if present)
        load_dotenv()
        data: Dict[str, Any] = {}
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            if isinstance(raw, dict):
                data = raw

        providers: Dict[str, ProviderSettings] = {}
        models: Dict[str, Dict[str, ModelSettings]] = {}
        default_provider: str | None = None
        default_models: Dict[str, list[str]] = {}

        # defaults (provider -> [model list])
        default_block = data.get("default", {}) or {}
        provider_block = default_block.get("provider", {}) or {}
        if isinstance(provider_block, dict) and provider_block:
            default_provider = next(iter(provider_block.keys()))
            for p_name, model_list in provider_block.items():
                if isinstance(model_list, list):
                    default_models[p_name] = [str(m) for m in model_list]

        # 1) providers (may include nested models)
        for name, conf in (data.get("providers", {}) or {}).items():
            conf = conf or {}
            api_base = conf.get("api_base")
            api_key = conf.get("api_key")
            api_org = conf.get("api_org")
            api_project = conf.get("api_project")
            proxy = conf.get("proxy")

            if isinstance(api_base, str):
                api_base = resolve_env_placeholder(api_base, provider_name=name, field_name="api_base")
            if isinstance(api_key, str):
                api_key = resolve_env_placeholder(api_key, provider_name=name, field_name="api_key")
            if isinstance(api_org, str):
                api_org = resolve_env_placeholder(api_org, provider_name=name, field_name="api_org")
            if isinstance(api_project, str):
                api_project = resolve_env_placeholder(api_project, provider_name=name, field_name="api_project")
            if isinstance(proxy, str):
                proxy = resolve_env_placeholder(proxy, provider_name=name, field_name="proxy")

            providers[name] = ProviderSettings(
                name=name,
                api_base=api_base,
                api_key=api_key,
                extra={
                    k: v
                    for k, v in conf.items()
                    if k not in ("api_base", "api_key", "api_org", "api_project", "proxy", "models")
                },
            )

            provider_models = conf.get("models", {}) or {}
            if provider_models:
                models.setdefault(name, {})
                for model_name, params in provider_models.items():
                    models[name][model_name] = ModelSettings(
                        name=model_name,
                        params=params or {},
                    )

        # 2) backward compatible: top-level models
        for provider, model_map in (data.get("models", {}) or {}).items():
            models.setdefault(provider, {})
            for model_name, params in (model_map or {}).items():
                if model_name in models[provider]:
                    continue
                models[provider][model_name] = ModelSettings(
                    name=model_name,
                    params=params or {},
                )

        return cls(
            providers=providers,
            models=models,
            default_provider=default_provider,
            default_models=default_models,
        )

    def provider(self, name: str) -> ProviderSettings:
        if name not in self.providers:
            raise ValueError(f"Unknown provider: {name}")
        return self.providers[name]

    def model(self, provider: str, model: str) -> ModelSettings:
        if provider not in self.models:
            raise ValueError(f"No models configured for provider: {provider}")
        if model not in self.models[provider]:
            raise ValueError(f"Unknown model '{model}' for provider '{provider}'")
        return self.models[provider][model]
