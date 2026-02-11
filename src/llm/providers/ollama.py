"""
Ollama 本地 LLM Provider
API: http://localhost:11434/api/chat
"""
from __future__ import annotations

import json
from typing import List, Dict, Any
from urllib import request, error

from ..base import LLMClient, Message, ProviderSettings


class OllamaProvider:
    """Ollama provider (local)"""

    def __init__(self, settings: ProviderSettings) -> None:
        self._base = (settings.api_base or "http://localhost:11434").rstrip("/")
        self._api_key = settings.api_key
        self._extra = settings.extra or {}

    def call(self, messages: List[Message], *, model: str, params: Dict[str, Any]) -> str:
        url = f"{self._base}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        options = dict(params or {})
        if options:
            payload["options"] = options

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = request.Request(url, data=data, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
        except error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}") from e

        try:
            data = json.loads(body)
            message = data.get("message") or {}
            content = message.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            return content
        except Exception as e:
            raise RuntimeError(f"Ollama response parse error: {e}") from e
