"""Knowledge provider stub (Phase 2)."""

from __future__ import annotations

from ...types import AgentRequest, TaskPlan
from ..types import ProviderResult


class KnowledgeProvider:
    name = "knowledge"

    async def provide(self, req: AgentRequest, plan: TaskPlan) -> ProviderResult:
        return ProviderResult(
            slot_name=self.name,
            value={"enabled": False, "reason": "Phase 2 knowledge not implemented"},
            status="stub",
        )
