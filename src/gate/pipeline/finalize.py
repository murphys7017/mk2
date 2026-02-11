from __future__ import annotations

from ..types import GateDecision, GateOutcome, GateAction, GateContext, GateWip, Scene


class FinalizeStage:
    """收敛为 GateDecision / GateOutcome"""

    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            action = wip.action_hint or GateAction.SINK

            decision = GateDecision(
                action=action,
                scene=scene,
                session_key=obs.session_key or "",
                target_worker=ctx.system_session_key if scene == Scene.SYSTEM else None,
                model_tier=wip.model_tier,
                response_policy=wip.response_policy,
                tool_policy=wip.tool_policy,
                score=wip.score,
                reasons=wip.reasons[: ctx.config.get_policy(scene).max_reasons],
                tags=wip.tags,
                fingerprint=wip.fingerprint,
            )

            outcome = GateOutcome(decision=decision, emit=wip.emit, ingest=wip.ingest)
            wip.features["outcome"] = outcome

            if ctx.metrics:
                ctx.metrics.processed_total += 1
                ctx.metrics.inc_scene(scene.value)
                ctx.metrics.inc_action(action.value)
                if action == GateAction.DROP:
                    ctx.metrics.dropped_total += 1
                elif action == GateAction.SINK:
                    ctx.metrics.sunk_total += 1
                elif action == GateAction.DELIVER:
                    ctx.metrics.delivered_total += 1
        except Exception as e:
            # 最后阶段不要抛出异常，只记录
            wip.reasons.append(f"finalize_error:{e}")
