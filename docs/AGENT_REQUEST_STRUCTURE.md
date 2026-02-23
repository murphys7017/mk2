# AgentRequest 结构清单

## 概述
`AgentRequest` 是 Agent 处理流程的输入，包含四个主要部分：**当前观察**、**网关决策**、**会话状态** 和 **时间戳**。

---

## 📋 顶层结构

```
AgentRequest
├── obs                    # Observation      - 本次收到的消息/事件
├── gate_decision          # GateDecision    - 网关是否通过、使用哪个模型、预算
├── session_state          # SessionState    - 会话历史、处理统计
├── now                    # datetime        - 当前时间戳（UTC）
└── gate_hint              # GateHint        - (可选) gate_decision.hint 的副本
```

---

## 1️⃣ obs: Observation (当前观察)

**用途**：本次请求中收到的消息或事件

### 字段列表

| 字段 | 类型 | 说明 |
|------|------|------|
| `obs_id` | str | 唯一观察ID (UUID格式) |
| `obs_type` | ObservationType | 事件类型: `MESSAGE` / `WORLD_DATA` / `ALERT` / `CONTROL` / `SCHEDULE` / `SYSTEM` |
| `source_name` | str | 事件来源: `text_input` / `agent:speaker` / 等 |
| `source_kind` | SourceKind | 来源类别: `EXTERNAL` (用户) / `INTERNAL` (系统) |
| `timestamp` | datetime | 事件发生时间 (UTC) |
| `received_at` | datetime | 事件接收时间 (UTC) |
| `session_key` | str | 会话ID (如 `dm:demo_user`) |
| `actor` | Actor | 事件触发者信息 |
| `payload` | MessagePayload | 事件内容 (文本、附件等) |
| `evidence` | EvidenceRef | 原始证据引用 (审计/回放用) |
| `quality_flags` | set | 质量标记集合 (如 `EMPTY_CONTENT`) |
| `confidence` | float \| None | 置信度 |
| `tags` | set | 标签集合 |
| `metadata` | dict | 自定义元数据 |

### 子字段详解

#### `actor`: Actor
```
actor_id      # 用户ID 或 系统ID (如 'demo_user', 'agent')
actor_type    # 类型: 'user' / 'system' / 'service' / 'unknown'
display_name  # 显示名称 (可选)
tenant_id     # 租户ID (可选)
extra         # 扩展字段 {}
```

#### `payload`: MessagePayload
```
text          # 消息正文 (如 '很好')
attachments   # 附件列表 []
mentions      # @提及列表 []
reply_to      # 回复的消息ID (可选)
extra         # 扩展字段 {}
```

#### `evidence`: EvidenceRef
```
raw_event_id  # 原始事件ID (如 'text_input:2')
raw_event_uri # 原始数据URI (可选)
signature     # 签名 (可选)
extra         # 扩展字段 {}
```

---

## 2️⃣ gate_decision: GateDecision (网关决策)

**用途**：安全网关对本次请求的决策 (是否通过、使用哪个模型、预算)

### 字段列表

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | GateAction | 决策: `BLOCK` / `DELIVER` / `HOLD` |
| `scene` | Scene | 场景分类: `DIALOGUE` / `COMMAND` / `TOOL_USE` / ... |
| `session_key` | str | 会话ID (同 obs.session_key) |
| `target_worker` | str \| None | 指定的处理器 (可选) |
| `model_tier` | str | 模型等级: `low` / `standard` / `high` |
| `response_policy` | str | 响应策略: `respond_now` / `delayed` / `noresponse` |
| `tool_policy` | str \| None | 工具调用策略 (可选) |
| `score` | float | 风险评分 (0.0 ~ 1.0) |
| `reasons` | list | 决策理由标签 (如 `['user_dialogue_safe_valve']`) |
| `tags` | dict | 分类标签 {} |
| `fingerprint` | str | 决策指纹 (用于去重/审计) |
| `hint` | GateHint | 详细的资源预算提示 |

#### `hint`: GateHint
```
model_tier          # 模型等级 (同上)
response_policy     # 响应策略 (同上)
budget              # BudgetSpec - 详见下表
reason_tags         # 决策理由 ['user_dialogue_safe_valve']
debug               # 调试信息 {}
```

#### `budget`: BudgetSpec (资源预算)
```
budget_level        # 预算等级: 'tiny' / 'small' / 'medium' / 'large'
time_ms             # 时间预算: 500 毫秒
max_tokens          # 最大tokens: 256
max_parallel        # 最大并行任务数: 1
evidence_allowed    # 是否允许证据收集: False
max_tool_calls      # 最大工具调用数: 0
can_search_kb       # 是否可搜索知识库: True
can_call_tools      # 是否可调用工具: True
auto_clarify        # 是否自动澄清: True
fallback_mode       # 是否回退模式: False
```

---

## 3️⃣ session_state: SessionState (会话状态)

**用途**：当前会话的历史和统计信息

### 字段列表

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_key` | str | 会话ID (如 `dm:demo_user`) |
| `created_at` | float | 会话创建时间戳 (Unix epoch) |
| `last_active_at` | float | 最后活动时间戳 |
| `processed_total` | int | 已处理观察总数: 3 |
| `error_total` | int | 错误总数: 0 |
| `recent_obs` | deque | 最近观察列表 (maxlen=20) |
| `now` | datetime | 当前时间 (UTC) |
| `gate_hint` | GateHint | 网关提示 |

### `recent_obs` 详解

**结构**：`deque[Observation]` (最多保存 20 条)

每条都是一个完整的 `Observation` 对象，包含：
- 历史的用户消息
- 历史的 Agent 回复
- 其他系统事件

**示例**（本请求中的 recent_obs）：

```
recent_obs = [
  1. 用户消息 "你好"
     ├─ obs_id: affe23ed3d44484ebf2a0def72f7e8e6
     ├─ text: "你好"
     └─ timestamp: 2026-02-21 13:30:41

  2. Agent 回复 "这是一个默认回复。"
     ├─ obs_id: 9a1ab85cee4f453a9d51f4e2b24769df
     ├─ text: "这是一个默认回复。"
     └─ timestamp: 2026-02-21 13:30:41

  3. 用户消息 "很好"
     ├─ obs_id: 3f81181db06840199d8289944c12a989
     ├─ text: "很好"
     └─ timestamp: 2026-02-21 13:30:45
]
```

---

## 4️⃣ now: datetime (当前时间)

当前处理时的 UTC 时间戳。

**示例**：`2026-02-21 13:30:45.016357 +00:00`

---

## 5️⃣ gate_hint: GateHint (可选)

通常是 `gate_decision.hint` 的副本，包含详细的预算和资源限制。

---

## 📊 快速查看清单

在你的 Agent 处理逻辑中，常见的查询：

```python
async def handle(self, req: AgentRequest) -> AgentOutcome:
    # 用户输入的文本
    user_text = req.obs.payload.text
    
    # 用户ID
    user_id = req.obs.actor.actor_id
    
    # 会话ID
    session_id = req.session_key
    
    # 网关是否通过
    is_allowed = req.gate_decision.action == GateAction.DELIVER
    
    # 使用哪个模型
    model_tier = req.gate_decision.model_tier  # "low" / "standard" / "high"
    
    # 时间预算（毫秒）
    time_budget = req.gate_hint.budget.time_ms  # 500
    
    # token 预算
    token_budget = req.gate_hint.budget.max_tokens  # 256
    
    # 历史对话（最近 20 条）
    history = req.session_state.recent_obs
    
    # 会话保活时间
    session_age = req.now.timestamp() - req.session_state.created_at
```

---

## 🔍 本例数据示例

```
当前观察:
  ├─ obs_id: 3f81181db06840199d8289944c12a989
  ├─ 消息: "很好"
  ├─ 用户: demo_user
  └─ 时间: 2026-02-21 13:30:45

网关决策:
  ├─ 动作: DELIVER (允许通过)
  ├─ 场景: DIALOGUE
  ├─ 模型等级: low
  ├─ 响应策略: respond_now
  ├─ 预算: tiny (500ms, 256 tokens)
  └─ 理由: user_dialogue_safe_valve

会话状态:
  ├─ 会话ID: dm:demo_user
  ├─ 处理次数: 3
  ├─ 错误次数: 0
  └─ 历史消息: 3 条

当前时间:
  └─ 2026-02-21 13:30:45 (UTC)
```

---

## 📝 常用代码片段

### 提取关键信息
```python
from src.agent.types import AgentRequest

def extract_request_summary(req: AgentRequest) -> dict:
    return {
        "obs_id": req.obs.obs_id,
        "text": req.obs.payload.text,
        "user_id": req.obs.actor.actor_id,
        "session_id": req.session_key,
        "gate_action": req.gate_decision.action.value,
        "model_tier": req.gate_decision.model_tier,
        "time_budget_ms": req.gate_hint.budget.time_ms,
        "token_budget": req.gate_hint.budget.max_tokens,
        "history_length": len(req.session_state.recent_obs),
        "is_allowed": req.gate_decision.action.value == "deliver",
    }
```

### 检查网关配额
```python
def check_budget(req: AgentRequest) -> tuple[int, int]:
    """返回 (可用时间, 可用token)"""
    budget = req.gate_hint.budget
    return budget.time_ms, budget.max_tokens
```

### 遍历对话历史
```python
for obs in req.session_state.recent_obs:
    print(f"[{obs.actor.actor_type}] {obs.payload.text}")
    # [user] 你好
    # [system] 这是一个默认回复。
    # [user] 很好
```

---
