from __future__ import annotations

from ..types import GateAction, GateContext, GateWip, Scene, GateHint
from ...schemas.observation import ObservationType


class PolicyMapper:
    """根据 score 和 scene policy 生成决策，应用 overrides 规则"""

    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            policy = ctx.config.scene_policy(scene)
            overrides = ctx.config.overrides
            source_name = getattr(obs, "source_name", "") or ""
            actor_id = obs.actor.actor_id if getattr(obs, "actor", None) else None
            is_agent_generated = source_name.startswith("agent:") or actor_id == "agent"

            # ========== NEW: User Dialogue UX Safety Valve ==========
            # 防止用户对话消息被沉默 SINK
            if (
                scene == Scene.DIALOGUE
                and obs.obs_type == ObservationType.MESSAGE
                and obs.actor
                and obs.actor.actor_type == "user"
                and wip.action_hint != GateAction.DROP  # 除非被硬 DROP
            ):
                # 强制用户对话消息 DELIVER
                wip.action_hint = GateAction.DELIVER
                wip.reasons.append("user_dialogue_safe_valve")
                
                # 初始化 GateHint
                wip.gate_hint = GateHint(
                    model_tier=policy.default_model_tier or "low",
                    response_policy=policy.default_response_policy or "respond_now",
                    budget=ctx.config.select_budget(wip.score, scene),
                    reason_tags=["user_dialogue_safe_valve"],
                )
                return

            # ========== Override Rule Priority (High to Low) ==========
            # 优先级从高到低应用 overrides，drop 优先于 deliver
            
            # 1. emergency_mode (最高优先级)
            if overrides.emergency_mode:
                wip.action_hint = GateAction.SINK
                wip.model_tier = "low"
                wip.response_policy = policy.default_response_policy
                wip.reasons.append("override=emergency")
                emergency_budget = ctx.config.budget_for_level("tiny")
                emergency_budget.time_ms = min(emergency_budget.time_ms, 300)
                emergency_budget.max_tokens = min(emergency_budget.max_tokens, 128)
                emergency_budget.evidence_allowed = False
                emergency_budget.max_tool_calls = 0
                emergency_budget.can_search_kb = False
                emergency_budget.can_call_tools = False
                wip.gate_hint = GateHint(
                    model_tier="low",
                    response_policy="ack",
                    budget=emergency_budget,
                    reason_tags=["emergency_mode"],
                )
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
                if (not is_agent_generated) and obs.session_key in overrides.deliver_sessions:
                    wip.action_hint = GateAction.DELIVER
                    wip.model_tier = policy.default_model_tier
                    wip.response_policy = policy.default_response_policy
                    wip.reasons.append("override=deliver_session")
                    deliver_override = True

            # 5. deliver_actors (强制 DELIVER 指定用户)
            if not deliver_override and hasattr(overrides, 'deliver_actors') and overrides.deliver_actors:
                if (not is_agent_generated) and hasattr(obs, 'actor') and obs.actor and obs.actor.actor_id in overrides.deliver_actors:
                    wip.action_hint = GateAction.DELIVER
                    wip.model_tier = policy.default_model_tier
                    wip.response_policy = policy.default_response_policy
                    wip.reasons.append("override=deliver_actor")
                    deliver_override = True

            # ========== Standard Policy (如无 deliver override) ==========
            if not deliver_override:
                if wip.action_hint is not None:
                    wip.reasons.append("action_hint")
                    # 初始化 gate_hint
                    if wip.gate_hint is None:
                        wip.gate_hint = GateHint(
                            model_tier=wip.model_tier or "low",
                            response_policy=wip.response_policy or "respond_now",
                            budget=ctx.config.select_budget(wip.score, scene),
                            reason_tags=wip.reasons,
                        )
                    return

                # 直通策略：MESSAGE 标准路径默认放行为 DELIVER
                if obs.obs_type == ObservationType.MESSAGE:
                    wip.action_hint = GateAction.DELIVER
                    wip.reasons.append("deliver_passthrough")
                else:
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
            
            # ========== Initialize GateHint for all paths ==========
            if wip.gate_hint is None:
                wip.gate_hint = GateHint(
                    model_tier=wip.model_tier or "low",
                    response_policy=wip.response_policy or "respond_now",
                    budget=ctx.config.select_budget(wip.score, scene),
                    reason_tags=wip.reasons,
                )
        except Exception as e:
            wip.reasons.append(f"policy_error:{e}")
