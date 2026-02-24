"""AgentQueen：Agent Phase 0 编排核心。"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from loguru import logger

from ..schemas.observation import (
    Actor,
    MessagePayload,
    Observation,
    ObservationType,
    SourceKind,
)
from .context import ContextBuilder, RecentObsContextBuilder
from .planner import HybridPlanner, LLMPlanner, Planner, RulePlanner
from .planner.validator import normalize_task_plan
from .pools import AgentPoolRouter, Aggregator, ChatPool, DraftAggregator, Pool, PoolRouter
from .registry import AgentConfigRegistry
from .speaker import AgentSpeaker, Speaker
from .types import AgentOutcome, AgentRequest, ContextPack, TaskPlan

# Deprecated alias: 旧代码可能从 queen 导入 Plan
Plan = TaskPlan


class AgentQueen:
    """
    Agent 总编排器（Phase 0）。

    固定流程：
    planner -> context_builder -> pool_router.pick -> pool.run -> aggregator -> speaker
    """

    def __init__(
        self,
        *,
        planner: Optional[Planner] = None,
        context_builder: Optional[ContextBuilder] = None,
        pool_router: Optional[PoolRouter] = None,
        aggregator: Optional[Aggregator] = None,
        speaker: Optional[Speaker] = None,
        registry: Optional[AgentConfigRegistry] = None,
    ) -> None:
        self.registry = registry or AgentConfigRegistry()
        self._config = self.registry.load()
        self.planner: Planner = planner or self._build_planner()
        self.context_builder: ContextBuilder = context_builder or RecentObsContextBuilder()
        self.pool_router: PoolRouter = pool_router or AgentPoolRouter()
        self.aggregator: Aggregator = aggregator or DraftAggregator()
        self.speaker: Speaker = speaker or AgentSpeaker()
        self._builtin_chat_pool = ChatPool()

    def _build_planner(self) -> Planner:
        planner_cfg = self.registry.get_planner_config()
        kind = str(planner_cfg.get("kind", "rule")).lower()
        if kind in {"hybrid", "hybrid_stub"}:
            return HybridPlanner(config=planner_cfg)
        if kind in {"llm", "llm_stub"}:
            return LLMPlanner(config=planner_cfg)
        return RulePlanner()

    async def handle(self, req: AgentRequest) -> AgentOutcome:
        """执行 Agent 主流程并返回可回灌 Observation。"""
        started = time.perf_counter()
        trace: Dict[str, Any] = {
            "planner": {},
            "context": {},
            "pool": {},
            "aggregation": {},
            "speaker": {},
            "fallback_triggered": False,
        }
        errors: list[str] = []

        plan = await self._safe_plan(req, trace, errors)
        ctx = await self._safe_context(req, plan, trace, errors)
        pool = self._safe_pick_pool(req, plan, trace, errors)
        raw = await self._safe_pool_run(req, plan, ctx, pool, trace, errors)
        final_text = await self._safe_aggregate(req, plan, ctx, raw, trace, errors)
        out_obs = self._safe_speak(req, final_text, plan, pool, trace, errors)

        fallback_triggered = bool(errors) or bool(trace.get("pool", {}).get("fallback"))
        trace["fallback_triggered"] = fallback_triggered
        if errors:
            trace["error"] = "; ".join(errors)
        trace["planner_kind"] = str(plan.meta.get("planner_kind", "rule"))
        trace["task_type"] = plan.task_type
        trace["pool_id"] = pool.pool_id
        trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        out_obs.metadata = dict(out_obs.metadata or {})
        out_obs.metadata["fallback"] = fallback_triggered

        return AgentOutcome(
            emit=[out_obs],
            trace=trace,
            error=trace.get("error"),
        )

    async def _safe_plan(
        self,
        req: AgentRequest,
        trace: Dict[str, Any],
        errors: list[str],
    ) -> TaskPlan:
        try:
            plan = await self.planner.plan(req)
            plan = normalize_task_plan(plan, planner_kind=getattr(self.planner, "kind", "unknown"))
            trace["planner"] = {
                "planner_kind": plan.meta.get("planner_kind"),
                "task_type": plan.task_type,
                "pool_id": plan.pool_id,
                "rule_guess": plan.meta.get("rule_guess"),
                "llm_called": plan.meta.get("llm_called"),
                "llm_parse_ok": plan.meta.get("llm_parse_ok"),
                "fallback_reason": plan.meta.get("fallback_reason"),
                "confidence": plan.meta.get("confidence"),
                "reason": plan.meta.get("reason"),
            }
            logger.debug(f"Agent planner output: {plan}")
            return plan
        except Exception as exc:
            logger.exception(f"Agent planner failed: {exc}")
            errors.append(f"planner:{exc}")
            fallback = normalize_task_plan(
                TaskPlan(
                    task_type="chat",
                    pool_id="chat",
                    required_context=("recent_obs",),
                    meta={
                        "strategy": "single_pass",
                        "complexity": "low",
                        "confidence": 0.3,
                        "reason": "planner_exception_fallback",
                    },
                ),
                planner_kind="rule_fallback",
            )
            trace["planner"] = {
                "planner_kind": fallback.meta.get("planner_kind"),
                "task_type": fallback.task_type,
                "pool_id": fallback.pool_id,
                "fallback": True,
                "error": str(exc),
            }
            return fallback

    async def _safe_context(
        self,
        req: AgentRequest,
        plan: TaskPlan,
        trace: Dict[str, Any],
        errors: list[str],
    ) -> ContextPack:
        try:
            ctx = await self.context_builder.build(req, plan)
            trace["context"] = {
                "required_context": list(plan.required_context),
                "slots_hit": dict(ctx.slots_hit or {}),
                "recent_obs_count": len(ctx.recent_obs),
            }
            return ctx
        except Exception as exc:
            logger.exception(f"Agent context builder failed: {exc}")
            errors.append(f"context:{exc}")
            recent_obs = list(req.session_state.recent_obs or [])
            ctx = ContextPack(
                recent_obs=recent_obs,
                slots_hit={"recent_obs": len(recent_obs) > 0},
                meta={"fallback": True},
            )
            trace["context"] = {
                "required_context": list(plan.required_context),
                "slots_hit": dict(ctx.slots_hit),
                "recent_obs_count": len(ctx.recent_obs),
                "fallback": True,
                "error": str(exc),
            }
            return ctx

    def _safe_pick_pool(
        self,
        req: AgentRequest,
        plan: TaskPlan,
        trace: Dict[str, Any],
        errors: list[str],
    ) -> Pool:
        try:
            pool = self.pool_router.pick(req, plan)
            if pool is None:
                raise RuntimeError("pool_router.pick returned None")
        except Exception as exc:
            logger.exception(f"Agent pool router failed: {exc}")
            errors.append(f"pool_router:{exc}")
            pool = self._fallback_pool()
            trace["pool"] = {
                "requested_pool_id": plan.pool_id,
                "pool_name": type(pool).__name__,
                "pool_id": pool.pool_id,
                "fallback": True,
                "error": str(exc),
            }
            return pool

        fallback = pool.pool_id != plan.pool_id
        trace["pool"] = {
            "requested_pool_id": plan.pool_id,
            "pool_name": type(pool).__name__,
            "pool_id": pool.pool_id,
            "fallback": fallback,
        }
        return pool

    async def _safe_pool_run(
        self,
        req: AgentRequest,
        plan: TaskPlan,
        ctx: ContextPack,
        pool: Pool,
        trace: Dict[str, Any],
        errors: list[str],
    ) -> Dict[str, Any]:
        try:
            raw = await pool.run(req, plan, ctx)
            trace["pool"]["raw_keys"] = list(raw.keys())
            return raw
        except Exception as exc:
            logger.exception(f"Agent pool run failed: {exc}")
            errors.append(f"pool_run:{exc}")

            fallback_pool = self._fallback_pool()
            trace["pool"]["error"] = str(exc)
            trace["pool"]["fallback"] = True
            trace["pool"]["fallback_pool_id"] = fallback_pool.pool_id
            try:
                raw = await fallback_pool.run(req, plan, ctx)
                trace["pool"]["raw_keys"] = list(raw.keys())
                return raw
            except Exception as fallback_exc:
                logger.exception(f"Agent fallback pool run failed: {fallback_exc}")
                errors.append(f"fallback_pool_run:{fallback_exc}")
                return {"draft": "我刚才处理时出现了问题，请重试一次。"}

    def _fallback_pool(self) -> Pool:
        router_fallback = getattr(self.pool_router, "fallback_pool", None)
        if callable(router_fallback):
            return router_fallback()
        return self._builtin_chat_pool

    async def _safe_aggregate(
        self,
        req: AgentRequest,
        plan: TaskPlan,
        ctx: ContextPack,
        raw: Dict[str, Any],
        trace: Dict[str, Any],
        errors: list[str],
    ) -> str:
        try:
            final_text = await self.aggregator.aggregate(req, plan, ctx, raw)
            trace["aggregation"] = {"length": len(final_text)}
            return final_text
        except Exception as exc:
            logger.exception(f"Agent aggregation failed: {exc}")
            errors.append(f"aggregation:{exc}")
            fallback_text = raw.get("draft") if isinstance(raw, dict) else ""
            fallback_text = str(fallback_text).strip() if fallback_text else ""
            if not fallback_text:
                fallback_text = "我处理到聚合阶段出现问题，请再试一次。"
            trace["aggregation"] = {
                "fallback": True,
                "error": str(exc),
                "length": len(fallback_text),
            }
            return fallback_text

    def _safe_speak(
        self,
        req: AgentRequest,
        final_text: str,
        plan: TaskPlan,
        pool: Pool,
        trace: Dict[str, Any],
        errors: list[str],
    ) -> Observation:
        metadata = {
            "task_type": plan.task_type,
            "pool_id": pool.pool_id,
            "planner_kind": plan.meta.get("planner_kind"),
            "fallback": trace.get("fallback_triggered", False),
        }
        try:
            out_obs = self.speaker.speak(req, final_text, extra=metadata)
            out_obs.metadata = dict(out_obs.metadata or {})
            trace["speaker"] = {
                "source_name": out_obs.source_name,
                "actor_id": out_obs.actor.actor_id if out_obs.actor else None,
            }
            return out_obs
        except Exception as exc:
            logger.exception(f"Agent speaker failed: {exc}")
            errors.append(f"speaker:{exc}")
            trace["speaker"] = {"fallback": True, "error": str(exc)}
            return Observation(
                obs_type=ObservationType.MESSAGE,
                source_name="agent:speaker",
                source_kind=SourceKind.INTERNAL,
                session_key=req.obs.session_key,
                actor=Actor(actor_id="agent", actor_type="system", display_name="Agent"),
                payload=MessagePayload(
                    text=final_text or "我刚刚回复失败了，请再发一次。"
                ),
                metadata=dict(metadata),
            )


# 兼容导出：旧测试可能直接引用这些名字
DefaultPlanner = RulePlanner
DefaultContextBuilder = RecentObsContextBuilder
DefaultPoolRouter = AgentPoolRouter
DefaultAggregator = DraftAggregator
DefaultSpeaker = AgentSpeaker
