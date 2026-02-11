"""
DefaultAgentOrchestrator: Agent 编排器
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .types import AgentRequest, AgentResponse, Step
from .planner import RulePlanner
from .llm import LLMClient, GatewayLLM
from ..llm import LLMConfig
from .dialogue_agent import SimpleDialogueAgent
from .skills.time_skill import GetTimeSkill
from ..schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    MessagePayload,
)


class DefaultAgentOrchestrator:
    """默认 Agent 编排器"""
    
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config_path: str = "config/llm.yaml",
    ):
        self.planner = RulePlanner()
        if llm is not None:
            self.llm = llm
        else:
            cfg = LLMConfig.load(config_path)
            if provider is None:
                provider = cfg.default_provider or next(iter(cfg.providers.keys()))
            if model is None:
                preferred = cfg.default_models.get(provider) or []
                if preferred:
                    model = preferred[0]
                else:
                    model_map = cfg.models.get(provider, {})
                    if not model_map:
                        raise ValueError(f"No models configured for provider: {provider}")
                    model = next(iter(model_map.keys()))
            self.llm = GatewayLLM(provider=provider, model=model, config_path=config_path)
        self.dialogue_agent = SimpleDialogueAgent(self.llm)
        self.time_skill = GetTimeSkill()
    
    def handle(self, req: AgentRequest) -> AgentResponse:
        """处理 agent 请求"""
        try:
            # 1. 制定计划
            plan = self.planner.build_plan(req)
            
            # 2. 执行计划
            text = ""
            for step in plan.steps:
                if step.type == "SKILL" and step.target == "get_time":
                    text = self.time_skill.run()
                elif step.type == "AGENT" and step.target == "dialogue":
                    text = self.dialogue_agent.reply(req)
                else:
                    text = f"Unknown step: {step.type}:{step.target}"
            
            # 3. 构造响应观察
            response_obs = self._create_response_observation(
                req=req,
                text=text
            )
            
            return AgentResponse(
                emit=[response_obs],
                success=True
            )
        
        except Exception as e:
            return AgentResponse(
                emit=[],
                success=False,
                error=str(e)
            )
    
    def _create_response_observation(
        self,
        req: AgentRequest,
        text: str
    ) -> Observation:
        """创建响应观察"""
        now = datetime.now(timezone.utc)
        
        return Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="agent",
            source_kind=SourceKind.INTERNAL,
            timestamp=now,
            received_at=now,
            session_key=req.obs.session_key,  # 保持同一会话
            actor=Actor(
                actor_id="assistant",
                actor_type="system",
                display_name="AI Assistant",
            ),
            payload=MessagePayload(
                text=text,
            ),
            metadata={
                "agent": "orchestrator",
                "in_reply_to": req.obs.obs_id,
            },
        )
