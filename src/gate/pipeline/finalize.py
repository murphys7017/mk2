from __future__ import annotations

from ..types import GateDecision, GateOutcome, GateAction, GateContext, GateWip, Scene, GateHint


class FinalizeStage:
    """收敛为 GateDecision / GateOutcome"""

    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            action = wip.action_hint or GateAction.SINK
            
            # 确保 wip 有 gate_hint（防御性编程）
            gate_hint = wip.gate_hint if wip.gate_hint else GateHint()

            decision = GateDecision(
                action=action,
                scene=scene,
                session_key=obs.session_key or "",
                target_worker=ctx.system_session_key if scene == Scene.SYSTEM else None,
                model_tier=gate_hint.model_tier,
                response_policy=gate_hint.response_policy,
                tool_policy=wip.tool_policy,
                score=wip.score,
                reasons=wip.reasons[: ctx.config.get_policy(scene).max_reasons],
                tags=wip.tags,
                fingerprint=wip.fingerprint,
                hint=gate_hint,
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
