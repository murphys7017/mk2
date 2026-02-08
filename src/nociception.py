# src/nociception.py
# =========================
# 痛觉系统（Nociception）v0：错误聚合与保护反射
# Nociception v0: Pain aggregation & protection reflex
# =========================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal
import logging

from .schemas.observation import (
    Observation,
    ObservationType,
    Actor,
    AlertPayload,
    SourceKind,
)

logger = logging.getLogger(__name__)


# ============================================================
# 痛觉规范（ALERT payload.data 字段约定）
# Pain specification (ALERT payload.data field convention)
# ============================================================

PAIN_WINDOW_SECONDS = 60
PAIN_BURST_THRESHOLD = 5
ADAPTER_COOLDOWN_SECONDS = 300
DROP_WINDOW_SECONDS = 30
DROP_BURST_THRESHOLD = 50
FANOUT_SUPPRESS_SECONDS = 60


def make_pain_alert(
    *,
    source_kind: str,
    source_id: str,
    severity: Literal['low', 'medium', 'high', 'critical'] = "medium",
    message: str = "",
    session_key: Optional[str] = None,
    where: Optional[str] = None,
    exception_type: Optional[str] = None,
    tags: Optional[list[str]] = None,
    data_extra: Optional[Dict[str, Any]] = None,
) -> Observation:
    """
    创建标准化的疼痛 ALERT observation。

    Args:
        source_kind: "core" | "router" | "adapter" | "tool" | "skill" | "external" | "system"
        source_id: 例如 "timer", "text_input", "skill:qweather"
        severity: "low" | "medium" | "high" | "critical"
        message: 简短描述
        session_key: 默认为 "system"（痛觉汇聚点）
        where: 可选，形如 "AdapterClass.method"
        exception_type: 可选，异常类名
        tags: 可选标签，例如 ["exception", "timeout"]
        data_extra: 可选额外数据，会合并到 payload.data

    Returns:
        标准化的 Observation(obs_type=ALERT, session_key=system)
    """
    session_key = session_key or "system"

    # 构建标准化 data 字段
    data: Dict[str, Any] = {
        "source_kind": source_kind,
        "source_id": source_id,
    }

    if where:
        data["where"] = where
    if exception_type:
        data["exception_type"] = exception_type
    if tags:
        data["tags"] = tags

    if data_extra:
        data.update(data_extra)

    payload = AlertPayload(
        alert_type="pain",
        severity=severity,
        message=message,
        data=data,
    )

    obs = Observation(
        obs_type=ObservationType.ALERT,
        source_name=f"{source_kind}:{source_id}",
        source_kind=SourceKind.INTERNAL,
        session_key=session_key,
        actor=Actor(actor_id="system", actor_type="system"),
        payload=payload,
    )

    return obs


def extract_pain_key(obs: Observation) -> str:
    """
    从 ALERT observation 中抽取聚合 key。

    如果是标准化 pain alert，key = "source_kind:source_id"。
    否则 fallback 到 "unknown:unknown"。
    """
    if obs.obs_type != ObservationType.ALERT:
        return "unknown:unknown"

    if not isinstance(obs.payload, AlertPayload):
        return "unknown:unknown"

    data = obs.payload.data
    source_kind = data.get("source_kind", "unknown")
    source_id = data.get("source_id", "unknown")

    return f"{source_kind}:{source_id}"


def extract_pain_severity(obs: Observation) -> str:
    """从 ALERT 中提取 severity"""
    if obs.obs_type == ObservationType.ALERT and isinstance(obs.payload, AlertPayload):
        return obs.payload.severity
    return "unknown"
