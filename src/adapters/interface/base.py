# src/adapters/base.py
# =========================
# Adapter 基类（生命体风）
# Base adapter (life-like)
# =========================

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, Dict, Literal
from ...input_bus import AsyncInputBus
from ...schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    EvidenceRef,
    AlertPayload,
)


# =========================================
# 同步投递结果
# Sync publish result
# =========================================

@dataclass(frozen=True)
class PublishResult:
    """
    中文：publish_nowait 的结果
    English: result for publish_nowait
    """
    ok: bool
    dropped: bool = False
    reason: Optional[str] = None


# =========================================
# 输入总线协议（Adapter 侧：同步）
# Input bus protocol (sync for adapters)
# =========================================



# =========================================
# 健康状态（最小）
# Health status (minimal)
# =========================================

@dataclass
class AdapterHealth:
    """
    中文：Adapter 自检快照
    English: adapter health snapshot
    """
    name: str
    running: bool
    last_seen_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    consecutive_failures: int = 0


# =========================================
# BaseAdapter
# =========================================

class BaseAdapter(ABC):
    """
    中文：
      BaseAdapter = “感官器官”基类。
      它只负责：
        1) 生命周期 start/stop
        2) emit(Observation) 投递到总线
        3) 任何错误 -> ALERT Observation（生命体风：喊疼但不崩）

      不负责：
        - 决策（那是 Core/Gateway/Router）
        - 记忆（那是 Memory）
        - 上下文构建（那是 ContextBuilder）

    English:
      Base adapter for "sensory organs".
      Life-like: errors become ALERT observations, not crashes.
    """

    def __init__(
        self,
        *,
        name: str,
        source_kind: SourceKind = SourceKind.EXTERNAL,
    ) -> None:
        self.name = name
        self.source_kind = source_kind

        self._bus: Optional[AsyncInputBus] = None
        self._running: bool = False

        # 最小状态 / minimal state
        self._last_seen_at: Optional[datetime] = None
        self._last_error_at: Optional[datetime] = None
        self._consecutive_failures: int = 0

    # -------------------------
    # 生命周期 / Lifecycle
    # -------------------------

    def start(self, bus: AsyncInputBus) -> None:
        """
        中文：启动（幂等）
        English: start (idempotent)
        """
        if self._running:
            return
        self._bus = bus
        self._running = True
        try:
            self._on_start()
        except Exception as e:
            # 启动失败也要上报为 ALERT
            self._report_error(
                error=e,
                alert_type="adapter_start_error",
                message="Adapter 启动失败 / Adapter start failed",
                severity="high",
            )
            self._running = False

    def stop(self) -> None:
        """
        中文：停止（幂等）
        English: stop (idempotent)
        """
        if not self._running:
            return
        try:
            self._on_stop()
        except Exception as e:
            self._report_error(
                error=e,
                alert_type="adapter_stop_error",
                message="Adapter 停止失败 / Adapter stop failed",
                severity="medium",
            )
        finally:
            self._running = False
            self._bus = None

    @property
    def running(self) -> bool:
        return self._running

    def health(self) -> AdapterHealth:
        """
        中文：健康快照
        English: health snapshot
        """
        return AdapterHealth(
            name=self.name,
            running=self._running,
            last_seen_at=self._last_seen_at,
            last_error_at=self._last_error_at,
            consecutive_failures=self._consecutive_failures,
        )

    # -------------------------
    # 投递 / Emit (sync)
    # -------------------------

    def emit(self, obs: Observation) -> None:
        """
        中文：
          同步投递 Observation 到总线（不阻塞）。
          - 成功：更新 last_seen_at，清零连续失败
          - 失败（队列满/丢弃）：上报一个背压 ALERT
          - 异常：上报 emit_error ALERT

        English:
          Emit observation synchronously (non-blocking).
        """
        if not self._running or self._bus is None:
            return

        try:
            obs.validate()
            result = self._bus.publish_nowait(obs)

            if result.ok:
                self._last_seen_at = datetime.now(timezone.utc)
                self._consecutive_failures = 0
                return

            # 队列满/丢弃：生命体喊疼（但不要递归炸）
            self._report_error(
                error=RuntimeError(f"publish_nowait dropped: {result.reason}"),
                alert_type="input_bus_backpressure",
                message="输入总线背压/丢弃了观察事件 / Input bus dropped observation",
                evidence=obs.evidence,
                data={"drop_reason": result.reason},
                severity="medium",
            )

        except Exception as e:
            self._report_error(
                error=e,
                alert_type="adapter_emit_error",
                message="Observation 投递失败 / Failed to emit observation",
                evidence=getattr(obs, "evidence", None),
                severity="high",
            )

    # -------------------------
    # 子类 hook / subclass hooks
    # -------------------------

    @abstractmethod
    def _on_start(self) -> None:
        """
        中文：子类启动逻辑（连接/订阅/准备资源）
        English: subclass start hook
        """
        raise NotImplementedError

    @abstractmethod
    def _on_stop(self) -> None:
        """
        中文：子类停止逻辑（断开/释放资源）
        English: subclass stop hook
        """
        raise NotImplementedError

    # -------------------------
    # 错误 -> ALERT（生命体风）
    # Error -> ALERT (life-like)
    # -------------------------

    def _report_error(
        self,
        *,
        error: Exception,
        alert_type: str,
        message: str,
        evidence: Optional[EvidenceRef] = None,
        data: Optional[Dict[str, Any]] = None,
        severity: Literal['low', 'medium', 'high', 'critical'] = "medium",
    ) -> None:
        """
        中文：
          将错误转换为 ALERT Observation 并尝试投递。
          注意：这里绝不能因为投递失败而递归调用自己。

        English:
          Convert error into ALERT observation and try to publish.
          Never recurse on failures here.
        """
        self._last_error_at = datetime.now(timezone.utc)
        self._consecutive_failures += 1

        payload_data: Dict[str, Any] = {
            "adapter": self.name,
            "error_type": type(error).__name__,
            "error": str(error),
            "consecutive_failures": self._consecutive_failures,
        }
        if data:
            payload_data.update(data)

        now = datetime.now(timezone.utc)
        alert_obs = Observation(
            obs_type=ObservationType.ALERT,
            source_name=self.name,
            source_kind=self.source_kind,
            timestamp=now,
            received_at=now,
            session_key="system:alerts",
            actor=Actor(actor_id="system", actor_type="system", display_name="System"),
            payload=AlertPayload(
                alert_type=alert_type,
                severity=severity,
                message=message,
                data=payload_data,
            ),
            evidence=evidence or EvidenceRef(),
            metadata={},
        )

        # 尝试投递 alert：失败就吞掉（不递归）
        if self._running and self._bus is not None:
            try:
                alert_obs.validate()
                self._bus.publish_nowait(alert_obs)
            except Exception:
                pass
