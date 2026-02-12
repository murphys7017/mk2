"""Agent module"""
# MVP v2 新接口
from .orchestrator import DefaultAgentOrchestrator
from .types import (
    AgentRequest,
    AgentOutcome,
    InfoPlan,
    EvidencePack,
    EvidenceItem,
    AnswerDraft,
    AnswerSpec,
)

# 向后兼容
from .types import (
    AgentResponse,
    Plan,
    Step,
)

__all__ = [
    # MVP v2
    "DefaultAgentOrchestrator",
    "AgentRequest",
    "AgentOutcome",
    "InfoPlan",
    "EvidencePack",
    "EvidenceItem",
    "AnswerDraft",
    "AnswerSpec",
    # 向后兼容
    "AgentResponse",
    "Plan",
    "Step",
]
