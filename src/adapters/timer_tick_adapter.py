# timer_tick_adapter.py
# =========================
# 定时 Tick 观察器（主动适配器示例）
# Timer tick observer (ActiveAdapter example)
# =========================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .interface.active_adapter import ActiveAdapter, ActiveAdapterConfig
from ..schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    EvidenceRef,
    SchedulePayload,
)


class TimerTickAdapter(ActiveAdapter):
    """
    中文：
      TimerTickAdapter = 最简单的主动观察器。
      每次 trigger() 就产生一个 SCHEDULE Observation：
        - obs_type = SCHEDULE
        - payload = SchedulePayload(schedule_id=..., data=...)

      典型用法：
        - 你的 scheduler 每隔 N 秒调用：adapter.trigger(reason="timer")
        - Core 想要一个“心跳事件”时调用：adapter.trigger(reason="heartbeat")

    English:
      TimerTickAdapter = simplest active observer.
      Each trigger() produces a SCHEDULE observation.
    """

    def __init__(
        self,
        *,
        name: str = "timer_tick",
        schedule_id: str = "tick",
        session_key: str = "system:timer",
        config: Optional[ActiveAdapterConfig] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        # 这里把 source_kind 设为 INTERNAL，表示系统内部观察
        super().__init__(name=name, config=config, source_kind=SourceKind.INTERNAL)

        self.schedule_id = schedule_id
        self.session_key = session_key
        self.extra_data = extra_data or {}

        # 中文：简单计数器，用于 data 里标记第几次 tick
        # English: a simple counter to label tick index
        self._tick_count: int = 0

    def _on_start(self) -> None:
        """
        中文：v0 不做循环，start 只表示“器官上线了”
        English: v0 no internal loop; start just means it's online
        """
        # 你也可以在这里 emit 一个 SYSTEM/WORLD_DATA 表示“我上线了”，但 v0 先不做
        return

    def _on_stop(self) -> None:
        """
        中文：v0 无需清理资源
        English: v0 no resources to cleanup
        """
        return

    def observe_once(self) -> Optional[Observation]:
        """
        中文：每次观测产生一个 tick 事件
        English: produce one tick observation per observe
        """
        self._tick_count += 1
        now = datetime.now(timezone.utc)

        payload = SchedulePayload(
            schedule_id=self.schedule_id,
            data={
                "tick": self._tick_count,
                "ts_iso": now.isoformat(),
                **self.extra_data,
            },
        )

        obs = Observation(
            obs_type=ObservationType.SCHEDULE,
            source_name=self.name,
            source_kind=SourceKind.INTERNAL,
            timestamp=now,
            received_at=now,
            session_key=self.session_key,
            actor=Actor(actor_id="system", actor_type="system", display_name="System"),
            payload=payload,
            evidence=EvidenceRef(
                raw_event_id=f"{self.schedule_id}:{self._tick_count}",
                extra={"schedule_id": self.schedule_id},
            ),
            metadata={
                "_kind": "timer_tick",
            },
        )

        obs.validate()
        return obs
