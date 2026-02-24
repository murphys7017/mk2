"""Memory provider stub (Phase 2)."""

from __future__ import annotations

from ...types import AgentRequest, TaskPlan
from ..types import ProviderResult


class MemoryProvider:
    name = "memory"

    async def provide(self, req: AgentRequest, plan: TaskPlan) -> ProviderResult:
        return ProviderResult(
            slot_name=self.name,
            value={"enabled": False, "reason": "Phase 2 memory not implemented"},
            status="stub",
        )
