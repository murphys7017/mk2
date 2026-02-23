# AgentRequest 结构清单（当前实现）

最后更新：2026-02-23

## 1. 顶层结构

`src/agent/types.py::AgentRequest`

```text
AgentRequest
├── obs: Observation
├── gate_decision: GateDecision
├── session_state: SessionState
├── now: datetime
└── gate_hint: GateHint | None
```

说明：

1. `gate_hint` 可选；若未传，会在 `__post_init__` 中回退到 `gate_decision.hint`。
2. 这是 Core 调用 AgentQueen 的输入契约。

## 2. `obs`（Observation）

定义：`src/schemas/observation.py`

常用字段：

1. `obs_id`
2. `obs_type`
3. `session_key`
4. `actor`
5. `payload`
6. `source_name`
7. `metadata`

在当前主链路中，只有满足以下条件才会触发 Agent：

1. `obs.obs_type == MESSAGE`
2. `gate_decision.action == DELIVER`

## 3. `gate_decision`（GateDecision）

定义：`src/gate/types.py`

关键字段：

1. `action`: `DROP | SINK | DELIVER`
2. `scene`: `DIALOGUE | GROUP | SYSTEM | TOOL_CALL | TOOL_RESULT | ALERT | UNKNOWN`
3. `score`
4. `reasons`
5. `hint`（`GateHint`）

注意：当前 GateAction 只有三种，不存在 `BLOCK/HOLD`。

## 4. `session_state`（SessionState）

定义：`src/session_router.py`

关键字段：

1. `session_key`
2. `processed_total`
3. `error_total`
4. `last_active_at`
5. `recent_obs`（`deque(maxlen=20)`）

该对象是运行态轻量状态，不是持久化 memory。

## 5. `now`（datetime）

1. 由 Core 在构造请求时注入。
2. 用于预算、超时、trace 记录。

## 6. `gate_hint`（GateHint）

定义：`src/gate/types.py`

字段：

1. `model_tier`
2. `response_policy`
3. `budget`（`BudgetSpec`）
4. `reason_tags`
5. `debug`

`BudgetSpec` 常用项：

1. `time_ms`
2. `max_tokens`
3. `max_tool_calls`
4. `evidence_allowed`

## 7. 典型读取方式

```python
from src.gate.types import GateAction

async def handle(req):
    text = getattr(req.obs.payload, "text", "")
    if req.gate_decision.action != GateAction.DELIVER:
        return

    budget = req.gate_hint.budget if req.gate_hint else None
    max_tokens = budget.max_tokens if budget else 256
    recent_count = len(req.session_state.recent_obs)

    # do agent logic...
```

## 8. 常见误区

1. 误把 `SessionState` 当长期记忆：它只是运行态窗口。
2. 误以为 Gate 有 `BLOCK/HOLD`：当前仅 `DROP/SINK/DELIVER`。
3. 忽略回流保护：`agent:*` 消息不会再次触发 Agent。
