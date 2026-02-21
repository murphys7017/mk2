from __future__ import annotations
from dataclasses import dataclass
from loguru import logger
from typing import Any, Dict, Optional, Protocol

# 这些类型在你项目里已经存在：src/agent/types.py, src/schemas/observation.py
from src.agent.types import AgentRequest, AgentOutcome
from src.schemas.observation import Observation, ObservationType, Actor, MessagePayload

@dataclass
class Plan:
    task_type: str = "chat"
    pool_id: str = "chat"
    required_context: tuple[str, ...] = ("recent_obs",)  # 先最小化
    meta: Optional[Dict[str, Any]] = None

@dataclass
class ContextPack:
    recent_obs: list[Observation]
    # 以后再加 memory_summary / retrieved_docs / user_profile ...

class Planner(Protocol):
    async def plan(self, req: AgentRequest) -> Plan: ...

class ContextBuilder(Protocol):
    async def build(self, req: AgentRequest, plan: Plan) -> ContextPack: ...

class Pool(Protocol):
    pool_id: str
    async def run(self, req: AgentRequest, plan: Plan, ctx: ContextPack) -> Dict[str, Any]:
        """返回 draft / candidates / tool_suggestions 等，先随意 dict"""
        ...

class PoolRouter(Protocol):
    def pick(self, req: AgentRequest, plan: Plan) -> Pool: ...

class Aggregator(Protocol):
    async def postprocess(self, req: AgentRequest, plan: Plan, ctx: ContextPack, raw: Dict[str, Any]) -> str:
        """返回最终文本"""
        ...

class Speaker(Protocol):
    def speak(self, req: AgentRequest, final_text: str, extra: Optional[Dict[str, Any]] = None) -> Observation: ...

class DefaultPlanner:
    async def plan(self, req: AgentRequest) -> Plan:
        return Plan()
class DefaultContextBuilder:
    async def build(self, req: AgentRequest, plan: Plan) -> ContextPack:
        return ContextPack(recent_obs=[req.obs])
class DefaultPool:
    pool_id = "chat"
    async def run(self, req: AgentRequest, plan: Plan, ctx: ContextPack) -> Dict[str, Any]:
        return {"draft": "这是一个默认回复。"}
class DefaultPoolRouter:
    def pick(self, req: AgentRequest, plan: Plan) -> Pool:
        return DefaultPool()
class DefaultAggregator:
    async def postprocess(self, req: AgentRequest, plan: Plan, ctx: ContextPack, raw: Dict[str, Any]) -> str:
        return raw.get("draft", "")
class DefaultSpeaker:
    def speak(self, req: AgentRequest, final_text: str, extra: Optional[Dict[str, Any]] = None) -> Observation:
        return Observation(
            obs_id="out_obs_1",
            payload=MessagePayload(text=final_text),
            metadata=extra or {},
        )
    
    
class AgentQueen:
    """
    Agent 总编排器（= Orchestrator）
    - 输入：AgentRequest（由 Core 构造）
    - 输出：AgentOutcome.emit（由 Core 回灌到 bus）
    """
    def __init__(
        self, 
    ) -> None:
        self.planner: Planner = DefaultPlanner()  # 先不在 init 注入，后续改成抽象基类，或者直接写死一个简单实现
        self.context_builder: ContextBuilder = DefaultContextBuilder()
        self.pool_router: PoolRouter = DefaultPoolRouter()
        self.aggregator: Aggregator = DefaultAggregator()
        self.speaker: Speaker = DefaultSpeaker()
    # def __init__(
    #     self,
    #     planner: Planner,
    #     context_builder: ContextBuilder,
    #     pool_router: PoolRouter,
    #     aggregator: Aggregator,
    #     speaker: Speaker,
    # ):
    #     self.planner = planner
    #     self.context_builder = context_builder
    #     self.pool_router = pool_router
    #     self.aggregator = aggregator
    #     self.speaker = speaker

    async def handle(self, req: AgentRequest) -> AgentOutcome:
        logger.debug(f"AgentQueen handling request: {req}")
        trace: Dict[str, Any] = {}
        try:
            plan = await self.planner.plan(req)
            trace["plan"] = {"task_type": plan.task_type, "pool_id": plan.pool_id}

            ctx = await self.context_builder.build(req, plan)
            trace["ctx"] = {"recent_obs": len(ctx.recent_obs)}

            pool = self.pool_router.pick(req, plan)
            trace["pool"] = pool.pool_id

            raw = await pool.run(req, plan, ctx)
            trace["raw_keys"] = list(raw.keys())

            final_text = await self.aggregator.postprocess(req, plan, ctx, raw)

            out_obs = self.speaker.speak(req, final_text, extra={"pool": pool.pool_id})
            # 关键：metadata 必须是 dict，避免 Core 写 memory_turn_id 时炸
            out_obs.metadata = dict(out_obs.metadata or {})

            return AgentOutcome(emit=[out_obs], trace=trace, error=None)

        except Exception as e:
            # 你的文档也强调“任一步失败要 fallback，避免沉默黑洞”:contentReference[oaicite:9]{index=9}
            trace["exception"] = str(e)
            logger.error(f"AgentQueen encountered an exception: {e}")
            fallback_obs = self.speaker.speak(req, "我这边刚刚处理时出了一点问题，能再说一遍吗？", extra={"fallback": True})
            fallback_obs.metadata = dict(fallback_obs.metadata or {})
            return AgentOutcome(emit=[fallback_obs], trace=trace, error=str(e))