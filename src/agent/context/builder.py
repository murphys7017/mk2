"""上下文构建器（Phase 0：仅 recent_obs）。"""

from __future__ import annotations

from typing import Protocol

from ..types import AgentRequest, ContextPack, TaskPlan


class ContextBuilder(Protocol):
    """可插拔上下文构建器接口。"""

    async def build(self, req: AgentRequest, plan: TaskPlan) -> ContextPack:
        ...


class RecentObsContextBuilder:
    """最小上下文构建器，仅封装 session_state.recent_obs。"""

    async def build(self, req: AgentRequest, plan: TaskPlan) -> ContextPack:
        recent_obs = list(req.session_state.recent_obs or [])
        slots_hit = {
            slot: (slot == "recent_obs" and len(recent_obs) > 0)
            for slot in (plan.required_context or ("recent_obs",))
        }
        if "recent_obs" not in slots_hit:
            slots_hit["recent_obs"] = len(recent_obs) > 0
        return ContextPack(
            recent_obs=recent_obs,
            slots_hit=slots_hit,
            meta={"provider": "recent_obs"},
        )
