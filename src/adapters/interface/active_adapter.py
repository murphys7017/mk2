# active_adapter.py
# =========================
# 主动输入适配器（主动观察）
# Active adapter (proactive/pull)
# =========================

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Dict

from .base import BaseAdapter
from ...schemas.observation import (
    Observation,
    EvidenceRef,
)


@dataclass
class ActiveAdapterConfig:
    """
    中文：主动适配器配置（保持极简）
    English: Active adapter config (keep minimal)
    """
    min_interval_seconds: float = 0.0  # 最短触发间隔（0 表示不限制）
    # v0 不做复杂 backoff；后面如果要做，可以加 max_backoff 等


class ActiveAdapter(BaseAdapter):
    """
    中文：
      ActiveAdapter = 主动感官器官（你主动去观察世界）。
      典型用法：
        - 定时任务触发：adapter.trigger()
        - core 需要信息时触发：adapter.trigger()

      子类只需要实现：
        - observe_once() -> Observation | None

      生命体风：
        - observe_once 异常不会炸系统
        - 会转成 ALERT Observation 上报

    English:
      ActiveAdapter = proactive sensory organ.
      External scheduler/core calls trigger().
      Subclass implements observe_once().
      Errors become ALERT observations.
    """

    def __init__(
        self,
        *,
        name: str,
        config: Optional[ActiveAdapterConfig] = None,
        source_kind=None,  # 兼容 BaseAdapter 的 SourceKind（如需）
    ) -> None:
        if source_kind is None:
            super().__init__(name=name)
        else:
            super().__init__(name=name, source_kind=source_kind)

        self.config = config or ActiveAdapterConfig()

        # 中文：上一次触发时间（用于最短间隔节流）
        # English: last trigger time (for simple throttling)
        self._last_trigger_at: Optional[datetime] = None

    # -------------------------
    # 主动触发入口 / Trigger entry
    # -------------------------

    def trigger(self, *, reason: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """
        中文：
          触发一次主动观测：
            - 先做最短间隔节流（可选）
            - 调用 observe_once() 获取 Observation
            - 返回 None：表示“这次没观察到可用内容”，静默跳过
            - 异常：上报 ALERT（生命体喊疼）

          reason/context 只用于调试与告警 data，不参与决策。

        English:
          Trigger one proactive observation:
            - optional throttling
            - call observe_once()
            - None -> skip
            - exception -> report ALERT
        """
        if not self.running:
            # v0：未启动就忽略（也可以改成上报 system alert）
            return

        now = datetime.now(timezone.utc)

        # 简单节流：避免过于频繁的 trigger
        if self._is_throttled(now):
            return

        self._last_trigger_at = now

        try:
            obs = self.observe_once()
            if obs is None:
                return

            self.emit(obs)

        except Exception as e:
            # 主动观测失败：上报 ALERT
            self._report_error(
                error=e,
                alert_type="adapter_observe_error",
                message="主动观测失败 / Active observation failed",
                evidence=self._try_make_evidence(reason=reason),
                data={
                    "reason": reason,
                    "context_keys": list(context.keys())[:50] if isinstance(context, dict) else None,
                },
                severity="medium",  # v0 固定，后面你再做分级规则
            )

    @abstractmethod
    def observe_once(self) -> Optional[Observation]:
        """
        中文：
          子类实现：执行一次“观察世界”，返回 Observation。
          - 返回 Observation：会被 emit 进入系统
          - 返回 None：表示这次没有有效观察结果（不报警）
          - 抛异常：基类会转为 ALERT 上报

        English:
          Subclass: observe the world once.
          - return Observation -> emitted
          - return None -> skip
          - raise -> ALERT
        """
        raise NotImplementedError

    # -------------------------
    # 内部辅助 / Helpers
    # -------------------------

    def _is_throttled(self, now: datetime) -> bool:
        """
        中文：最短间隔节流（v0 简单版本）
        English: simple min-interval throttling (v0)
        """
        interval = float(self.config.min_interval_seconds or 0.0)
        if interval <= 0:
            return False

        if self._last_trigger_at is None:
            return False

        return now - self._last_trigger_at < timedelta(seconds=interval)

    def _try_make_evidence(self, *, reason: Optional[str]) -> EvidenceRef:
        """
        中文：主动观测一般没有 raw_event_id，这里给一个轻量 evidence。
        English: proactive observations usually have no raw_event_id; create lightweight evidence.
        """
        extra = {}
        if reason:
            extra["reason"] = reason
        return EvidenceRef(raw_event_id=None, raw_event_uri=None, extra=extra)
