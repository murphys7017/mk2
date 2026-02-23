"""
LLM provider integration tests (opt-in).
Set env vars to enable live API calls.
"""
from __future__ import annotations

import os
import pytest

from src.llm import LLMConfig, LLMProvider


# 集成测试开关：只有设置 RUN_LLM_LIVE_TESTS=1 才执行
SKIP_INTEGRATION = os.getenv("RUN_LLM_LIVE_TESTS") != "1"


@pytest.mark.integration
@pytest.mark.skipif(SKIP_INTEGRATION, reason="需要设置 RUN_LLM_LIVE_TESTS=1 才能运行 LLM 集成测试")
def test_bailian_api_call_live() -> None:
    """
    Live test for Bailian OpenAI-compatible endpoint.
    Required env vars:
      - BAILIAN_API_KEY
      - BAILIAN_MODEL
      - (optional) BAILIAN_API_BASE
    """
    cfg = LLMConfig.load("config/llm.yaml")

    if "bailian" not in cfg.providers:
        raise AssertionError("bailian provider not configured in config/llm.yaml")

    provider = "bailian"
    preferred = cfg.default_models.get(provider) or []
    if preferred:
        model = preferred[0]
    else:
        model_map = cfg.models.get(provider, {})
        if not model_map:
            raise AssertionError("No bailian models configured in config/llm.yaml")
        model = next(iter(model_map.keys()))

    # Ensure provider exists; override key/base via default_params if needed
    gateway = LLMProvider(
        provider=provider,
        model=model,
        config=cfg,
        default_params={
            "temperature": 0.2,
            "max_tokens": 128,
        },
    )

    try:
        text = gateway.call([
            {"role": "user", "content": "say ok"},
        ])
    except RuntimeError as e:
        # 处理配额耗尽错误（Bailian 免费额度）
        if "403" in str(e) and "FreeTierOnly" in str(e):
            pytest.skip(f"Bailian 免费额度已用完，跳过测试: {e}")
        raise  # 其他错误仍然失败

    assert isinstance(text, str)
    assert len(text.strip()) > 0


@pytest.mark.integration
def test_ollama_api_call_live() -> None:
    """
    Live test for local Ollama.
    Required env vars:
      - OLLAMA_MODEL
      - (optional) OLLAMA_API_BASE
    """
    cfg = LLMConfig.load("config/llm.yaml")

    if "ollama" not in cfg.providers:
        raise AssertionError("ollama provider not configured in config/llm.yaml")

    provider = "ollama"
    preferred = cfg.default_models.get(provider) or []
    if preferred:
        model = preferred[0]
    else:
        model_map = cfg.models.get(provider, {})
        if not model_map:
            raise AssertionError("No ollama models configured in config/llm.yaml")
        model = next(iter(model_map.keys()))

    gateway = LLMProvider(
        provider=provider,
        model=model,
        config=cfg,
        default_params={"temperature": 0.2},
    )

    text = gateway.call([
        {"role": "user", "content": "say ok"},
    ])

    assert isinstance(text, str)
    assert len(text.strip()) > 0
