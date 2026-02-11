"""
百炼 OpenAI 兼容接口 Provider
默认 endpoint: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
"""
from __future__ import annotations

import json
from typing import List, Dict, Any
from urllib import request, error

from ..base import LLMClient, Message, ProviderSettings


def _normalize_openai_params(params: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        if k in ("maxTokens", "max_tokens"):
            normalized["max_tokens"] = v
        elif k in ("topP", "top_p"):
            normalized["top_p"] = v
        elif k in ("presencePenalty", "presence_penalty"):
            normalized["presence_penalty"] = v
        elif k in ("frequencyPenalty", "frequency_penalty"):
            normalized["frequency_penalty"] = v
        else:
            normalized[k] = v
    return normalized


class BailianOpenAIProvider:
    """Bailian OpenAI-compatible provider"""

    def __init__(self, settings: ProviderSettings) -> None:
        base = settings.api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._base = base.rstrip("/")
        self._api_key = settings.api_key
        self._extra = settings.extra or {}

    def call(self, messages: List[Message], *, model: str, params: Dict[str, Any]) -> str:
        url = f"{self._base}/chat/completions"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        payload.update(_normalize_openai_params(params))

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = request.Request(url, data=data, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Bailian HTTP {e.code}: {detail}") from e
        except error.URLError as e:
            raise RuntimeError(f"Bailian connection error: {e}") from e

        try:
            data = json.loads(body)
            choices = data.get("choices", [])
            if not choices:
                return ""
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            return content
        except Exception as e:
            raise RuntimeError(f"Bailian response parse error: {e}") from e
