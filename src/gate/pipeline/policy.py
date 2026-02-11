from __future__ import annotations

from ..types import GateAction, GateContext, GateWip, Scene


class PolicyMapper:
    """根据 score 和 scene policy 生成决策，应用 overrides 规则"""

    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            policy = ctx.config.scene_policy(scene)
            overrides = ctx.config.overrides

            # ========== Override Rule Priority (High to Low) ==========
            # 优先级从高到低应用 overrides，drop 优先于 deliver
            
            # 1. emergency_mode (最高优先级)
            if overrides.emergency_mode:
                wip.action_hint = GateAction.SINK
                wip.model_tier = "low"
                wip.response_policy = policy.default_response_policy
                wip.reasons.append("override=emergency")
                return

            # 2. drop_sessions (强制 DROP 指定会话)
            if hasattr(overrides, 'drop_sessions') and overrides.drop_sessions:
                if obs.session_key in overrides.drop_sessions:
                    wip.action_hint = GateAction.DROP
                    wip.reasons.append("override=drop_session")
                    return

            # 3. drop_actors (强制 DROP 指定用户)
            if hasattr(overrides, 'drop_actors') and overrides.drop_actors:
                if hasattr(obs, 'actor') and obs.actor and obs.actor.actor_id in overrides.drop_actors:
                    wip.action_hint = GateAction.DROP
                    wip.reasons.append("override=drop_actor")
                    return

            # 4. deliver_sessions (强制 DELIVER 指定会话)
            deliver_override = False
            if hasattr(overrides, 'deliver_sessions') and overrides.deliver_sessions:
                if obs.session_key in overrides.deliver_sessions:
                    wip.action_hint = GateAction.DELIVER
                    wip.model_tier = policy.default_model_tier
                    wip.response_policy = policy.default_response_policy
                    wip.reasons.append("override=deliver_session")
                    deliver_override = True

            # 5. deliver_actors (强制 DELIVER 指定用户)
            if not deliver_override and hasattr(overrides, 'deliver_actors') and overrides.deliver_actors:
                if hasattr(obs, 'actor') and obs.actor and obs.actor.actor_id in overrides.deliver_actors:
                    wip.action_hint = GateAction.DELIVER
                    wip.model_tier = policy.default_model_tier
                    wip.response_policy = policy.default_response_policy
                    wip.reasons.append("override=deliver_actor")
                    deliver_override = True

            # ========== Standard Policy (如无 deliver override) ==========
            if not deliver_override:
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

            # 6. force_low_model (仅在 DELIVER 时生效)
            if overrides.force_low_model and wip.action_hint == GateAction.DELIVER:
                wip.model_tier = "low"
                wip.reasons.append("override=force_low_model")
        except Exception as e:
            wip.reasons.append(f"policy_error:{e}")
