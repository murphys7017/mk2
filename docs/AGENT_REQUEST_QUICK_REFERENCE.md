# AgentRequest 快速参考（当前实现）

最后更新：2026-02-23

## 一屏速查

| 模块 | 字段 | 说明 |
|---|---|---|
| Observation | `req.obs.payload.text` | 当前用户输入文本（MESSAGE 场景） |
| Gate | `req.gate_decision.action` | `DROP/SINK/DELIVER` |
| Gate Hint | `req.gate_hint.budget.max_tokens` | token 预算 |
| Session | `req.session_state.recent_obs` | 最近 20 条 observation |
| Time | `req.now` | 当前处理时间（UTC） |

## 最常用判断

```python
from src.gate.types import GateAction

def can_process(req) -> bool:
    return req.gate_decision.action == GateAction.DELIVER
```

## 常用提取模板

```python
def summarize(req):
    hint = req.gate_hint or req.gate_decision.hint
    budget = hint.budget if hint else None
    return {
        "session": req.obs.session_key,
        "text": getattr(req.obs.payload, "text", ""),
        "action": req.gate_decision.action.value,
        "scene": req.gate_decision.scene.value,
        "max_tokens": getattr(budget, "max_tokens", None),
        "time_ms": getattr(budget, "time_ms", None),
        "recent_obs_count": len(req.session_state.recent_obs),
    }
```

## 当前契约来源

1. `src/agent/types.py`
2. `src/gate/types.py`
3. `src/session_router.py`
4. `src/schemas/observation.py`
