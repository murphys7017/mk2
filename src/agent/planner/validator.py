"""TaskPlan 归一化与解析校验。"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from ..types import TaskPlan

ALLOWED_TASK_TYPES = {"chat", "code", "plan", "creative"}
ALLOWED_STRATEGIES = {"single_pass", "draft_critique"}
ALLOWED_COMPLEXITIES = {"simple", "multi_step", "open_ended"}
ALLOWED_CONTEXT_SLOTS = {
    "recent_obs",
    "gate_hint",
    "memory_summary",
    "retrieved_docs",
    "tool_results",
}


def normalize_task_plan(plan: TaskPlan, *, planner_kind: str) -> TaskPlan:
    """补齐字段并规整非法值。"""
    return normalize_task_plan_payload(
        {
            "task_type": plan.task_type,
            "pool_id": plan.pool_id,
            "required_context": list(plan.required_context or ()),
            "meta": dict(plan.meta or {}),
        },
        planner_kind=planner_kind,
    )


def normalize_task_plan_payload(payload: Mapping[str, Any], *, planner_kind: str) -> TaskPlan:
    """从 dict-like payload 归一化出合法 TaskPlan。"""
    raw_task_type = str(payload.get("task_type", "chat")).strip().lower()
    task_type = raw_task_type if raw_task_type in ALLOWED_TASK_TYPES else "chat"

    raw_pool_id = str(payload.get("pool_id", "") or "").strip().lower()
    pool_id = raw_pool_id if raw_pool_id else task_type

    required_context = _normalize_required_context(payload.get("required_context"))

    raw_meta = payload.get("meta", {})
    meta = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}

    # 将顶层透传字段并入 meta（便于调用方塞扩展 trace）
    passthrough = (
        "rule_guess",
        "llm_called",
        "llm_parse_ok",
        "fallback_reason",
        "llm_error",
    )
    for key in passthrough:
        if key in payload and key not in meta:
            meta[key] = payload.get(key)

    meta["strategy"] = _normalize_strategy(meta.get("strategy"))
    meta["complexity"] = _normalize_complexity(meta.get("complexity"))
    meta["confidence"] = _normalize_confidence(meta.get("confidence"))
    meta["reason"] = _normalize_reason(meta.get("reason"))
    meta["planner_kind"] = planner_kind

    return TaskPlan(
        task_type=task_type,
        pool_id=pool_id,
        required_context=required_context,
        meta=meta,
    )


def _normalize_required_context(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ("recent_obs",)

    normalized: list[str] = []
    for item in raw:
        val = str(item).strip().lower()
        if val in ALLOWED_CONTEXT_SLOTS and val not in normalized:
            normalized.append(val)

    if not normalized:
        return ("recent_obs",)
    return tuple(normalized)


def _normalize_strategy(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    if val in ALLOWED_STRATEGIES:
        return val
    return "single_pass"


def _normalize_complexity(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    if val in ALLOWED_COMPLEXITIES:
        return val
    return "simple"


def _normalize_confidence(raw: Any) -> float:
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.6
    if val < 0:
        return 0.0
    if val > 1:
        return 1.0
    return val


def _normalize_reason(raw: Any) -> str:
    val = str(raw or "").strip()
    return val or "normalized"
