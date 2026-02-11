from __future__ import annotations

from ..types import GateAction, GateContext, GateWip, Scene


class PolicyMapper:
    """根据 score 和 scene policy 生成决策"""

    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            policy = ctx.config.scene_policy(scene)
            overrides = ctx.config.overrides

            if overrides.emergency_mode:
                wip.action_hint = GateAction.SINK
                wip.model_tier = "low"
                wip.response_policy = policy.default_response_policy
                wip.reasons.append("emergency_mode")
                return

            if wip.action_hint is not None:
                wip.reasons.append("action_hint")
                return

            if wip.score >= policy.deliver_threshold:
                wip.action_hint = GateAction.DELIVER
            elif wip.score >= policy.sink_threshold:
                wip.action_hint = GateAction.SINK
            else:
                wip.action_hint = policy.default_action

            wip.model_tier = policy.default_model_tier
            wip.response_policy = policy.default_response_policy

            if overrides.force_low_model and wip.action_hint == GateAction.DELIVER:
                wip.model_tier = "low"
                wip.reasons.append("force_low_model")
        except Exception as e:
            wip.reasons.append(f"policy_error:{e}")
