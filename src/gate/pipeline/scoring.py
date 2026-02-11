from __future__ import annotations

from ..types import GateContext, GateWip, Scene


class ScoringStage:
    """最小评分逻辑"""

    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            score = 0.0
            scene = wip.scene or Scene.UNKNOWN
            rules = ctx.config.rules

            if scene == Scene.DIALOGUE:
                w = rules.dialogue.weights
                score += w.get("base", 0.10)
                if wip.features.get("has_mention"):
                    score += w.get("mention", 0.40)
                if wip.features.get("has_question"):
                    score += w.get("question_mark", 0.15)
                text_len = wip.features.get("text_len", 0)
                if isinstance(text_len, int) and text_len >= rules.dialogue.long_text_len:
                    score += w.get("long_text", 0.10)

                if isinstance(wip.features.get("text_len"), int):
                    text = (getattr(obs.payload, "text", "") or "").lower()
                    for kw, weight in rules.dialogue.keywords.items():
                        if kw in text:
                            score += weight
            elif scene == Scene.GROUP:
                w = rules.group.weights
                score += w.get("base", 0.05)
                if wip.features.get("has_bot_mention"):
                    score += w.get("mention", 0.60)
                actor_id = wip.features.get("actor_id")
                if actor_id and actor_id in rules.group.whitelist_actors:
                    score += w.get("whitelist_actor", 0.25)
            elif scene == Scene.ALERT:
                score += 0.6
            elif scene == Scene.SYSTEM:
                w = rules.system.weights
                score += w.get("base", 0.0)
            elif scene == Scene.TOOL_CALL:
                score += 0.7
            elif scene == Scene.TOOL_RESULT:
                score += 0.5

            # 小幅加权
            text_len = wip.features.get("text_len", 0)
            if isinstance(text_len, int) and text_len > 0:
                score += min(text_len / 200.0, 0.2)

            wip.score = max(0.0, min(score, 1.0))
        except Exception as e:
            wip.reasons.append(f"score_error:{e}")
