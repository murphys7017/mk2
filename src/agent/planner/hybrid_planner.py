"""HybridPlanner：规则预判 + LLM 规划 + 规则兜底。"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional

from ..types import AgentRequest, TaskPlan
from .llm_planner import LLMPlanner
from .rule_planner import RulePlanner
from .validator import normalize_task_plan_payload


class HybridPlanner:
    """先跑 RulePlanner，再尝试 LLMPlanner，失败时回退规则结果。"""

    kind = "hybrid"

    def __init__(
        self,
        *,
        config: Optional[Mapping[str, Any]] = None,
        rule_planner: Optional[RulePlanner] = None,
        llm_planner: Optional[LLMPlanner] = None,
    ) -> None:
        self._cfg = dict(config or {})
        self._rule = rule_planner or RulePlanner()
        self._llm = llm_planner or LLMPlanner(config=self._cfg)
        self._timeout_seconds = _to_positive_float(self._cfg.get("timeout_seconds"), default=8.0)

    async def plan(self, req: AgentRequest) -> TaskPlan:
        rule_plan = await self._rule.plan(req)
        rule_guess = {
            "task_type": rule_plan.task_type,
            "pool_id": rule_plan.pool_id,
        }

        try:
            llm_plan = await asyncio.wait_for(
                self._llm.plan(
                    req,
                    rule_plan=rule_plan,
                    recent_obs_count=len(req.session_state.recent_obs or []),
                ),
                timeout=self._timeout_seconds,
            )
            payload = {
                "task_type": llm_plan.task_type,
                "pool_id": llm_plan.pool_id,
                "required_context": list(llm_plan.required_context),
                "meta": dict(llm_plan.meta or {}),
                "rule_guess": rule_guess,
                "llm_called": True,
                "llm_parse_ok": True,
            }
            return normalize_task_plan_payload(payload, planner_kind="hybrid_llm")
        except Exception as exc:
            payload = {
                "task_type": rule_plan.task_type,
                "pool_id": rule_plan.pool_id,
                "required_context": list(rule_plan.required_context),
                "meta": dict(rule_plan.meta or {}),
                "rule_guess": rule_guess,
                "llm_called": True,
                "llm_parse_ok": False,
                "fallback_reason": str(exc),
                "llm_error": str(exc),
            }
            return normalize_task_plan_payload(payload, planner_kind="hybrid_rule_fallback")


def _to_positive_float(raw: Any, *, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
