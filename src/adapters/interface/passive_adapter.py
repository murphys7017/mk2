# passive_adapter.py
# =========================
# 被动输入适配器（外界触发）
# Passive adapter (reactive/push)
# =========================

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Dict, Set

from .base import BaseAdapter  # 按你的项目结构调整 import
from ...schemas.observation import (
    Observation,
    ObservationType,
    EvidenceRef,
)


@dataclass
class PassiveAdapterConfig:
    """
    中文：被动适配器配置（保持极简）
    English: Passive adapter config (keep minimal)
    """
    enable_dedup: bool = False            # 是否去重（基于 raw_event_id）
    dedup_max_ids: int = 10_000           # 去重缓存最大ID数量（简单做法）


class PassiveAdapter(BaseAdapter):
    """
    中文：
      PassiveAdapter = 被动感官器官（外界刺激你）。
      外界每来一个 raw 事件，调用 on_raw(raw)。

      你写具体平台适配器时：
        - 只要实现 to_observation(raw) -> Observation | None
        - 然后在平台回调里调用 self.on_raw(payload)

      生命体风：
        - 解析失败/异常不会炸系统
        - 会转成 ALERT Observation 上报

    English:
      PassiveAdapter = reactive sensory organ.
      External events call on_raw(raw).
      Subclass only implements to_observation(raw).
      Errors become ALERT observations.
    """

    def __init__(
        self,
        *,
        name: str,
        config: Optional[PassiveAdapterConfig] = None,
        source_kind=None,  # 兼容你 BaseAdapter 的 SourceKind 参数（如果你需要）
    ) -> None:
        # 允许 source_kind 透传给 BaseAdapter（你也可以直接删除这段兼容）
        if source_kind is None:
            super().__init__(name=name)
        else:
            super().__init__(name=name, source_kind=source_kind)

        self.config = config or PassiveAdapterConfig()

        # 中文：简单的去重集合（只存 raw_event_id）
        # English: simple dedup set (stores raw_event_id)
        self._dedup_ids: Set[str] = set()

    # -------------------------
    # 子类无需重写 start/stop（沿用 BaseAdapter）
    # Subclass uses BaseAdapter lifecycle
    # -------------------------

    # -------------------------
    # 被动入口 / Reactive entry
    # -------------------------

    def on_raw(self, raw: Any) -> None:
        """
        中文：
          外界事件入口：把 raw 转成 Observation 并 emit。
          - 转换成功：emit
          - 返回 None：静默跳过（表示“不处理”）
          - 发生异常：上报 ALERT（生命体喊疼）

        English:
          Entry point for raw events.
          - Success -> emit
          - None -> skip silently
          - Exception -> report ALERT
        """
        if not self.running:
            # v0：未启动就忽略（也可以改为上报一个 system alert）
            return

        try:
            obs = self.to_observation(raw)
            if obs is None:
                return

            # 可选：去重（基于 evidence.raw_event_id）
            if self.config.enable_dedup:
                if self._is_duplicate(obs):
                    # 标记重复并（可选）直接丢弃
                    obs.quality_flags.add("DUPLICATE")
                    # v0：直接丢弃重复事件（避免双发）
                    return

            self.emit(obs)

        except Exception as e:
            # 转换失败：上报 ALERT
            self._report_error(
                error=e,
                alert_type="adapter_parse_error",
                message="被动事件解析失败 / Failed to parse raw event",
                evidence=self._try_extract_evidence(raw),
                data=self._safe_debug_data(raw),
                severity="medium",  # v0 先固定
            )

    @abstractmethod
    def to_observation(self, raw: Any) -> Optional[Observation]:
        """
        中文：
          子类实现：将平台 raw 事件转为 Observation。
          - 转不了：返回 None（不报警）
          - 解析失败：直接抛异常（基类会转 ALERT）

        English:
          Subclass: convert raw event to Observation.
          - Not applicable -> return None
          - Failure -> raise exception
        """
        raise NotImplementedError

    # -------------------------
    # 去重（可选）/ Dedup (optional)
    # -------------------------

    def _is_duplicate(self, obs: Observation) -> bool:
        """
        中文：基于 evidence.raw_event_id 做最简单的去重。
        English: simple dedup based on evidence.raw_event_id.
        """
        rid = obs.evidence.raw_event_id
        if not rid:
            return False

        if rid in self._dedup_ids:
            return True

        self._dedup_ids.add(rid)

        # 简单控制集合大小（v0：超过就清空；更优雅可以用 LRU）
        if len(self._dedup_ids) > self.config.dedup_max_ids:
            self._dedup_ids.clear()

        return False

    # -------------------------
    # 从 raw 里尽量提取 evidence（可选）
    # Try extract evidence from raw (optional)
    # -------------------------

    def _try_extract_evidence(self, raw: Any) -> EvidenceRef:
        """
        中文：
          尝试从 raw 里提取事件ID等证据（失败也没关系）。
          这里给一个非常宽松的默认实现：
          - raw 是 dict 且有 message_id/event_id/id -> raw_event_id
        English:
          Best-effort extraction of evidence from raw.
        """
        try:
            if isinstance(raw, dict):
                rid = (
                    raw.get("message_id")
                    or raw.get("event_id")
                    or raw.get("id")
                )
                if rid is not None:
                    return EvidenceRef(raw_event_id=str(rid), extra={})
        except Exception:
            pass
        return EvidenceRef()

    def _safe_debug_data(self, raw: Any) -> Dict[str, Any]:
        """
        中文：
          错误上报时带一点点 raw 摘要（避免把敏感/超大数据塞进去）。
        English:
          Attach a tiny summary for debugging (avoid huge/sensitive payload).
        """
        summary: Dict[str, Any] = {"adapter": self.name}
        try:
            if isinstance(raw, dict):
                # 只放 keys 列表，不放值（更安全）
                keys = list(raw.keys())
                summary["raw_keys"] = keys[:50]
            else:
                summary["raw_type"] = type(raw).__name__
        except Exception:
            pass
        return summary
