from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, List
from collections import deque

from ..types import GateAction, GateContext, GateWip
from ..pool.drop_pool import DropPool
from ..config import DropEscalationConfig
from ...nociception import make_pain_alert
from ...schemas.observation import Observation, ObservationType, AlertPayload
from ...schemas.observation import MessagePayload


@dataclass
class DropMonitor:
    window_seconds: float
    burst_threshold: int
    consecutive_threshold: int

    def __post_init__(self) -> None:
        self.timestamps: Deque[float] = deque()
        self.consecutive: int = 0

    def record_drop(self, now_ts: float) -> bool:
        self.timestamps.append(now_ts)
        self.consecutive += 1
        cutoff = now_ts - self.window_seconds
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()
        return len(self.timestamps) >= self.burst_threshold or self.consecutive >= self.consecutive_threshold

    def reset_consecutive(self) -> None:
        self.consecutive = 0


class HardBypass:
    """硬门控：过载保护 + drop 监控"""

    def __init__(self) -> None:
        self.drop_pool = DropPool(maxlen=200)
        self._monitor: DropMonitor | None = None

    def apply(self, obs: Observation, ctx: GateContext, wip: GateWip) -> None:
        try:
            cfg: DropEscalationConfig = ctx.config.drop_escalation
            if self._monitor is None:
                self._monitor = DropMonitor(
                    window_seconds=cfg.burst_window_sec,
                    burst_threshold=cfg.burst_count_threshold,
                    consecutive_threshold=cfg.consecutive_threshold,
                )

            # overload guard
            if ctx.system_health and ctx.system_health.get("overload"):
                wip.action_hint = GateAction.DROP
                wip.reasons.append("system_overload")
                alert = make_pain_alert(
                    source_kind="system",
                    source_id="gate_overload",
                    severity="high",
                    message="Gate overload detected",
                    session_key=ctx.system_session_key,
                    data_extra={"cooldown_seconds": cfg.cooldown_suggest_sec},
                )
                wip.emit.append(alert)
                return

            # drop tracking for alerts or unknown with empty content
            if obs.obs_type == ObservationType.ALERT:
                self._monitor.reset_consecutive()
                return

            # 空内容直接丢弃（避免噪声）
            if obs.obs_type == ObservationType.MESSAGE and isinstance(obs.payload, MessagePayload):
                if not (obs.payload.text or "").strip() and not obs.payload.attachments:
                    wip.action_hint = GateAction.DROP
                    wip.reasons.append("empty_content")

            if wip.action_hint == GateAction.DROP:
                self.drop_pool.ingest(obs)
                should_escalate = self._monitor.record_drop(ctx.now.timestamp())
                if should_escalate:
                    wip.tags["drop_burst"] = "true"
                    alert = make_pain_alert(
                        source_kind="gate",
                        source_id="drop_burst",
                        severity="medium",
                        message="Drop burst detected",
                        session_key=ctx.system_session_key,
                        data_extra={
                            "burst_window_sec": cfg.burst_window_sec,
                            "burst_count_threshold": cfg.burst_count_threshold,
                            "consecutive_threshold": cfg.consecutive_threshold,
                            "cooldown_seconds": cfg.cooldown_suggest_sec,
                        },
                    )
                    wip.emit.append(alert)
            else:
                self._monitor.reset_consecutive()
        except Exception as e:
            alert = make_pain_alert(
                source_kind="gate",
                source_id="hard_bypass_exception",
                severity="high",
                message=str(e),
                session_key=ctx.system_session_key,
            )
            wip.emit.append(alert)
