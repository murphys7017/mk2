"""规则 Planner（Phase 0 默认实现）。"""

from __future__ import annotations

from ..types import AgentRequest, TaskPlan
from .signals import extract_signals
from .types import PlannerInputView
from .validator import normalize_task_plan


class RulePlanner:
    """基于简单信号做任务类型路由。"""

    kind = "rule"

    async def plan(self, req: AgentRequest, view: PlannerInputView | None = None) -> TaskPlan:
        override_text = view.current_input_text if view is not None else None
        signals = extract_signals(req, text_override=override_text)
        reason = "dialogue_default"
        task_type = "chat"
        pool_id = "chat"
        complexity = "simple"
        confidence = 0.65
        strategy = "single_pass"

        if signals.has_code_signal:
            task_type = "code"
            pool_id = "code"
            complexity = "multi_step"
            confidence = 0.82
            reason = "code_signal"
        elif signals.has_plan_signal:
            task_type = "plan"
            pool_id = "plan"
            complexity = "multi_step"
            strategy = "draft_critique"
            confidence = 0.78
            reason = "plan_signal"
        elif signals.has_creative_signal:
            task_type = "creative"
            pool_id = "creative"
            complexity = "open_ended"
            confidence = 0.72
            reason = "creative_signal"

        raw = TaskPlan(
            task_type=task_type,
            pool_id=pool_id,
            required_context=("recent_obs",),
            meta={
                "strategy": strategy,
                "complexity": complexity,
                "confidence": confidence,
                "reason": reason,
            },
        )
        return normalize_task_plan(raw, planner_kind=self.kind)
