# text_input_adapter.py
# =========================
# 最简单的文本输入被动适配器（手动喂文本）
# Simplest passive text input adapter (manual feed)
# =========================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any, cast

from .interface.passive_adapter import PassiveAdapter, PassiveAdapterConfig
from ..schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    EvidenceRef,
    MessagePayload,
)


class TextInputAdapter(PassiveAdapter):
    """
    中文：
      TextInputAdapter = 最简单的被动输入适配器，用于把“用户文本”注入系统。
      适合：
        - 本地 CLI 测试
        - 单元测试
        - 没接平台前先跑通链路

      用法：
        adapter.ingest_text("你好", actor_id="user1", session_key="dm:user1")

    English:
      Simplest passive adapter to inject user text into the system.
    """

    def __init__(
        self,
        *,
        default_session_key: str = "dm:local",
        config: Optional[PassiveAdapterConfig] = None,
    ) -> None:
        super().__init__(name="text_input", config=config, source_kind=SourceKind.EXTERNAL)
        self.default_session_key = default_session_key

        # 中文：一个简单递增计数，用作 raw_event_id
        # English: simple counter to form raw_event_id
        self._seq: int = 0

    def _on_start(self) -> None:
        # 中文：无资源需要启动
        # English: no resources needed
        return

    def _on_stop(self) -> None:
        # 中文：无资源需要清理
        # English: no resources needed
        return

    # -------------------------
    # 你用这个方法“喂入”文本
    # Feed text into the adapter
    # -------------------------
    def ingest_text(
        self,
        text: str,
        *,
        actor_id: str = "user",
        session_key: Optional[str] = None,
        display_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        中文：把用户文本变成 raw dict，然后走 on_raw(raw) 统一流程。
        English: wrap text into a raw dict and pass to on_raw(raw).
        """
        self._seq += 1
        raw = {
            "text": text,
            "actor_id": actor_id,
            "session_key": session_key or self.default_session_key,
            "display_name": display_name,
            "message_id": f"{self.name}:{self._seq}",
            "metadata": metadata or {},
        }
        self.on_raw(raw)

    # -------------------------
    # PassiveAdapter 要求实现：raw -> Observation
    # PassiveAdapter required: raw -> Observation
    # -------------------------
    def to_observation(self, raw: Any) -> Optional[Observation]:
        """
        中文：
          支持 raw 为 dict，包含 text/actor_id/session_key。
          如果 raw 不是 dict 或缺少 text，就返回 None（静默跳过）。

        English:
          Accept dict raw with text/actor_id/session_key.
          Non-dict or missing text -> return None.
        """
        if not isinstance(raw, dict):
            return None

        text = raw.get("text")
        if not isinstance(text, str) or text.strip() == "":
            return None

        actor_id = raw.get("actor_id")
        session_key = raw.get("session_key")
        display_name = raw.get("display_name")

        msg_id = raw.get("message_id")
        metadata_raw = raw.get("metadata")
        meta = cast(Dict[str, Any], metadata_raw) if isinstance(metadata_raw, dict) else {}

        now = datetime.now(timezone.utc)

        obs = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name=self.name,
            source_kind=SourceKind.EXTERNAL,
            timestamp=now,
            received_at=now,
            session_key=str(session_key) if session_key is not None else None,
            actor=Actor(
                actor_id=str(actor_id) if actor_id is not None else None,
                actor_type="user",
                display_name=str(display_name) if display_name else None,
            ),
            payload=MessagePayload(text=text),
            evidence=EvidenceRef(raw_event_id=str(msg_id) if msg_id else None),
            metadata=meta,
        )

        obs.validate()
        return obs
