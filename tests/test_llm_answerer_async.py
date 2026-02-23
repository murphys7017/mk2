from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_llm_answerer_does_not_block_event_loop():
    pytest.skip("LLMAnswerer removed in agent rewrite; async LLM test pending redesign.")
