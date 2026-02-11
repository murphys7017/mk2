"""
LLM provider integration tests (opt-in).
Set env vars to enable live API calls.
"""
from __future__ import annotations

import os
import pytest

from src.llm import LLMConfig, LLMGateway


@pytest.mark.integration
def test_bailian_api_call_live() -> None:
    """
    Live test for Bailian OpenAI-compatible endpoint.
    Required env vars:
      - BAILIAN_API_KEY
      - BAILIAN_MODEL
      - (optional) BAILIAN_API_BASE
    """
    if os.getenv("RUN_LLM_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LLM_LIVE_TESTS=1 to enable live LLM tests")

    cfg = LLMConfig.load("config/llm.yaml")

    if "bailian" not in cfg.providers:
        pytest.skip("bailian provider not configured in config/llm.yaml")

    provider = "bailian"
    preferred = cfg.default_models.get(provider) or []
    if preferred:
        model = preferred[0]
    else:
        model_map = cfg.models.get(provider, {})
        if not model_map:
            pytest.skip("No bailian models configured in config/llm.yaml")
        model = next(iter(model_map.keys()))

    # Ensure provider exists; override key/base via default_params if needed
    gateway = LLMGateway(
        provider=provider,
        model=model,
        config=cfg,
        default_params={
            "temperature": 0.2,
            "max_tokens": 128,
        },
    )

    text = gateway.call([
        {"role": "user", "content": "say ok"},
    ])

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
    if os.getenv("RUN_LLM_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LLM_LIVE_TESTS=1 to enable live LLM tests")

    cfg = LLMConfig.load("config/llm.yaml")

    if "ollama" not in cfg.providers:
        pytest.skip("ollama provider not configured in config/llm.yaml")

    provider = "ollama"
    preferred = cfg.default_models.get(provider) or []
    if preferred:
        model = preferred[0]
    else:
        model_map = cfg.models.get(provider, {})
        if not model_map:
            pytest.skip("No ollama models configured in config/llm.yaml")
        model = next(iter(model_map.keys()))

    gateway = LLMGateway(
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
