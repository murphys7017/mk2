from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .types import GateOutcome, GateContext, GateWip, GateAction, Scene
from .config import GateConfig
from .metrics import GateMetrics
from .pipeline.base import DefaultGatePipeline
from .pool.sink_pool import SinkPool
from .pool.drop_pool import DropPool
from .pool.tool_pool import ToolPool
from ..schemas.observation import Observation, ObservationType


@dataclass
class DefaultGate:
    """
    Gate 入口（MVP）

    使用示例（在 Worker 中）：

        ctx = GateContext(
            now=datetime.now(timezone.utc),
            config=gate.config,
            system_session_key=core.system_session_key,
            metrics=gate.metrics,
            session_state=state,
            system_health={"overload": False},
        )
        outcome = gate.handle(obs, ctx)

        for emit_obs in outcome.emit:
            core.bus.publish_nowait(emit_obs)

        for ingest_obs in outcome.ingest:
            gate.ingest(ingest_obs, outcome.decision)

        if outcome.decision.action == GateAction.DELIVER:
            agent.handle(obs, outcome.decision)
    """

    config: GateConfig
    metrics: GateMetrics

    def __init__(self, config: Optional[GateConfig] = None, metrics: Optional[GateMetrics] = None) -> None:
        self.config = config or GateConfig()
        self.metrics = metrics or GateMetrics()

        self.pipeline = DefaultGatePipeline()
        self.sink_pool = SinkPool(maxlen=200)
        self.drop_pool = DropPool(maxlen=200)
        self.tool_pool = ToolPool(maxlen=200)

    def handle(self, obs: Observation, ctx: GateContext) -> GateOutcome:
        wip = GateWip()
        self.pipeline.run(obs, ctx, wip)

        outcome: GateOutcome | None = wip.features.get("outcome")
        if outcome is None:
            # fallback
            from .types import GateDecision
            decision = GateDecision(
                action=wip.action_hint or GateAction.SINK,
                scene=wip.scene or Scene.UNKNOWN,
                session_key=obs.session_key or "",
                score=wip.score,
                reasons=wip.reasons,
                tags=wip.tags,
                fingerprint=wip.fingerprint,
            )
            outcome = GateOutcome(decision=decision, emit=wip.emit, ingest=wip.ingest)

        # 生成 ingest（如果 pipeline 没有填写）
        if not outcome.ingest:
            if outcome.decision.action == GateAction.DROP:
                outcome.ingest.append(obs)
            elif outcome.decision.action == GateAction.SINK:
                outcome.ingest.append(obs)
            elif outcome.decision.action == GateAction.DELIVER:
                # DELIVER 默认不入池
                pass

        return outcome

    def ingest(self, obs: Observation, decision) -> None:
        if decision.action == GateAction.DROP:
            self.drop_pool.ingest(obs)
        elif decision.action == GateAction.SINK:
            # tool_result 默认进 tool_pool
            if decision.scene == Scene.TOOL_RESULT:
                self.tool_pool.ingest(obs)
            else:
                self.sink_pool.ingest(obs)
