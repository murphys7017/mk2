"""
DefaultAgentOrchestrator: Agent 编排器（MVP v2）
"""
from __future__ import annotations

import time
from typing import Optional, Any, Dict
from loguru import logger

from .types import AgentRequest, AgentOutcome
from .planner import Planner, RulePlanner
from .evidence import EvidenceRunner, StubEvidenceRunner
from .answerer import Answerer, LLMAnswerer
from .speaker import Speaker, DefaultSpeaker
from .post import PostProcessor, NoopPostProcessor


class DefaultAgentOrchestrator:
    """
    Agent 编排器 MVP 版本
    
    职责：
    - 协调 Planner → EvidenceRunner → Answerer → Speaker → PostProcessor
    - 完整的 trace 和错误处理
    - 返回 AgentOutcome（emit + trace / error）
    """
    
    def __init__(
        self,
        planner: Optional[Planner] = None,
        evidence_runner: Optional[EvidenceRunner] = None,
        answerer: Optional[Answerer] = None,
        speaker: Optional[Speaker] = None,
        post_processor: Optional[PostProcessor] = None,
        logger_instance: Optional[Any] = None,
        llm_provider: str = "bailian",
        llm_model: str = "qwen-max",
        llm_config_path: str = "config/llm.yaml",
    ) -> None:
        """初始化 Orchestrator"""
        self.planner = planner or RulePlanner()
        self.evidence_runner = evidence_runner or StubEvidenceRunner()
        self.answerer = answerer or LLMAnswerer(
            provider=llm_provider,
            model=llm_model,
            config_path=llm_config_path,
        )
        self.speaker = speaker or DefaultSpeaker()
        self.post_processor = post_processor or NoopPostProcessor()
        self.logger = logger_instance or logger
    
    async def handle(self, req: AgentRequest) -> AgentOutcome:
        """
        处理 Agent 请求
        
        流程：
        1. Planner: 决定需要什么信息
        2. EvidenceRunner: 收集证据
        3. Answerer: 生成回答
        4. Speaker: 转换成 Observation
        5. PostProcessor: 后处理
        
        所有步骤都有错误捕获，确保返回可控的 fallback。
        """
        trace: Dict[str, Any] = {
            "start_ts": time.time(),
            "steps": {}
        }
        
        try:
            # ============================================================
            # Step 1: Planning
            # ============================================================
            # self.logger.debug(f"[Orchestrator] Planning for obs_id={req.obs.obs_id}")
            try:
                info_plan, answer_spec = await self.planner.plan(req, gate_hint=req.gate_hint)
                trace["steps"]["planning"] = {
                    "sources": info_plan.sources,
                    "budget": info_plan.budget,
                }
                # self.logger.debug(f"[Orchestrator] Plan: sources={info_plan.sources}")
            except Exception as e:
                # self.logger.error(f"[Orchestrator] Planning failed: {e}")
                trace["steps"]["planning"] = {"error": str(e)}
                return self._fallback_outcome(
                    req=req,
                    trace=trace,
                    error=f"Planning failed: {e}"
                )
            
            # ============================================================
            # Step 2: Evidence Gathering
            # ============================================================
            # self.logger.debug(f"[Orchestrator] Gathering evidence for sources={info_plan.sources}")
            try:
                evidence = await self.evidence_runner.gather(req, info_plan)
                trace["steps"]["evidence"] = {
                    "items_count": len(evidence.items),
                    "stats": evidence.stats,
                }
                # self.logger.debug(f"[Orchestrator] Gathered {len(evidence.items)} evidence items")
            except Exception as e:
                # self.logger.error(f"[Orchestrator] Evidence gathering failed: {e}")
                trace["steps"]["evidence"] = {"error": str(e)}
                return self._fallback_outcome(
                    req=req,
                    trace=trace,
                    error=f"Evidence gathering failed: {e}"
                )
            
            # ============================================================
            # Step 3: Answering
            # ============================================================
            # self.logger.debug(f"[Orchestrator] Generating answer")
            try:
                draft = await self.answerer.answer(req, evidence, answer_spec)
                trace["steps"]["answering"] = {
                    "text_len": len(draft.text),
                    "meta": draft.meta,
                }
                # self.logger.debug(f"[Orchestrator] Generated answer ({len(draft.text)} chars)")
            except Exception as e:
                # self.logger.error(f"[Orchestrator] Answering failed: {e}")
                trace["steps"]["answering"] = {"error": str(e)}
                return self._fallback_outcome(
                    req=req,
                    trace=trace,
                    error=f"Answering failed: {e}"
                )
            
            # ============================================================
            # Step 4: Speaking
            # ============================================================
            # self.logger.debug(f"[Orchestrator] Rendering response observations")
            try:
                emit_msgs = await self.speaker.render(req, draft)
                trace["steps"]["speaking"] = {
                    "obs_count": len(emit_msgs),
                }
                # self.logger.debug(f"[Orchestrator] Rendered {len(emit_msgs)} observation(s)")
            except Exception as e:
                # self.logger.error(f"[Orchestrator] Speaking failed: {e}")
                trace["steps"]["speaking"] = {"error": str(e)}
                return self._fallback_outcome(
                    req=req,
                    trace=trace,
                    error=f"Speaking failed: {e}"
                )
            
            # ============================================================
            # Step 5: Post-processing
            # ============================================================
            # self.logger.debug(f"[Orchestrator] Post-processing")
            try:
                emit_post = await self.post_processor.after_reply(req, draft, evidence)
                trace["steps"]["post_processing"] = {
                    "obs_count": len(emit_post),
                }
                # self.logger.debug(f"[Orchestrator] Post-processing generated {len(emit_post)} observation(s)")
            except Exception as e:
                # self.logger.error(f"[Orchestrator] Post-processing failed: {e}")
                trace["steps"]["post_processing"] = {"error": str(e)}
                # 这一步如果失败，不影响主回复，只记录
                emit_post = []
            
            # ============================================================
            # Final: Combine and return
            # ============================================================
            trace["end_ts"] = time.time()
            trace["elapsed_ms"] = (trace["end_ts"] - trace["start_ts"]) * 1000
            
            # self.logger.debug(
            # f"[Orchestrator] Complete in {trace['elapsed_ms']:.1f}ms, "
            # f"emit {len(emit_msgs) + len(emit_post)} obs"
            # )
            
            return AgentOutcome(
                emit=emit_msgs + emit_post,
                trace=trace,
                error=None
            )
        
        except Exception as e:
            # 捕获任何未预期的异常
            # self.logger.exception(f"[Orchestrator] Unexpected error: {e}")
            return self._fallback_outcome(
                req=req,
                trace=trace,
                error=f"Unexpected error: {e}"
            )
    
    def _fallback_outcome(
        self,
        req: AgentRequest,
        trace: Dict[str, Any],
        error: str,
    ) -> AgentOutcome:
        """
        生成 fallback 结果（当某个步骤失败时）
        """
        from ..schemas.observation import Observation, ObservationType, Actor, MessagePayload, SourceKind
        
        # 构造简单的错误回复
        error_text = f"(agent_error) {error[:100]}"
        
        fallback_obs = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="agent:orchestrator_fallback",
            source_kind=SourceKind.INTERNAL,
            session_key=req.obs.session_key,
            actor=Actor(
                actor_id="agent",
                actor_type="system",
                display_name="Agent Assistant"
            ),
            payload=MessagePayload(text=error_text),
        )
        
        trace["end_ts"] = time.time()
        trace["elapsed_ms"] = (trace["end_ts"] - trace["start_ts"]) * 1000
        trace["fallback"] = True
        
        return AgentOutcome(
            emit=[fallback_obs],
            trace=trace,
            error=error
        )
