# AgentRequest 数据概览 - 本次实例

## 📌 快速摘要

| 类别 | 字段 | 值 |
|------|------|-----|
| **当前消息** | 用户ID | `demo_user` |
| | 消息内容 | `"很好"` |
| | 消息ID | `3f81181db06840199d8289944c12a989` |
| | 发送时间 | `2026-02-21 13:30:45` (UTC) |
| **会话** | 会话ID | `dm:demo_user` |
| | 消息总数 | 3 条 |
| | 创建时间 | `2026-02-21 13:30:41` |
| **网关** | 通过决策 | ✅ `DELIVER` (允许) |
| | 场景 | `DIALOGUE` (对话) |
| | 风险评分 | `0.11` (低风险) |
| | 响应模式 | `respond_now` (立即回复) |
| **资源分配** | 模型等级 | `low` (轻量模型) |
| | 时间预算 | `500` ms |
| | Token预算 | `256` |
| | 最大并行数 | `1` |
| | 是否允许搜索知识库 | ✅ Yes |
| | 是否允许调用工具 | ✅ Yes |

---

## 🔍 详细字段展开

### 1️⃣ obs: Observation (当前观察)

```
当前消息的完整信息：

┌─ 基础信息
│  ├─ obs_id: "3f81181db06840199d8289944c12a989"
│  ├─ obs_type: MESSAGE (消息类型)
│  ├─ source_name: "text_input" (来自文本输入)
│  └─ source_kind: EXTERNAL (外部来源)
│
├─ 时间信息
│  ├─ timestamp: 2026-02-21 13:30:45.015357 UTC
│  └─ received_at: 2026-02-21 13:30:45.015357 UTC
│
├─ 身份信息 (actor)
│  ├─ actor_id: "demo_user" ← 用户ID
│  ├─ actor_type: "user"
│  ├─ display_name: None
│  ├─ tenant_id: None
│  └─ extra: {}
│
├─ 载荷 (payload) - 消息内容
│  ├─ text: "很好" ← 用户说的内容
│  ├─ attachments: [] (无附件)
│  ├─ mentions: [] (无@提及)
│  ├─ reply_to: None (非回复)
│  └─ extra: {}
│
├─ 证据 (evidence)
│  ├─ raw_event_id: "text_input:2"
│  ├─ raw_event_uri: None
│  ├─ signature: None
│  └─ extra: {}
│
├─ 质量标记 (quality_flags): set() (无质量问题)
├─ 置信度 (confidence): None
├─ 标签 (tags): set() (无标签)
└─ 元数据 (metadata): {}
```

---

### 2️⃣ gate_decision: GateDecision (网关决策)

```
安全网关对此请求的决策：

┌─ 决策结果
│  ├─ action: DELIVER ✅ (允许通过，让 Agent 处理)
│  ├─ scene: DIALOGUE 💬 (场景: 日常对话)
│  ├─ session_key: "dm:demo_user"
│  └─ target_worker: None (无指定处理器)
│
├─ 资源配置
│  ├─ model_tier: "low" 📉 (使用轻量级模型)
│  ├─ response_policy: "respond_now" ⚡ (立即响应，不延迟)
│  ├─ tool_policy: None
│  └─ score: 0.11 (风险评分: 0～1, 0.11 = 低风险)
│
├─ 决策溯源
│  ├─ reasons: ["user_dialogue_safe_valve"] (理由: 用户对话安全阀)
│  ├─ tags: {} (无额外标签)
│  └─ fingerprint: "4f6ce7eeda646c1ea560c4a064f9aa07c70ec28d5c3f239577c966fddc140fee"
│        (用于去重和审计)
│
└─ 资源预算 (hint)
   └─ BudgetSpec
      ├─ budget_level: "tiny" 🎯
      ├─ time_ms: 500 (只能用 500 毫秒)
      ├─ max_tokens: 256 (回复最多 256 个token)
      ├─ max_parallel: 1 (顺序执行，不并行)
      ├─ evidence_allowed: False (不收集额外证据)
      ├─ max_tool_calls: 0 (不允许调用外部工具)
      ├─ can_search_kb: True ✅ (可以搜索知识库)
      ├─ can_call_tools: True ✅ (可以调用工具，但 max=0)
      ├─ auto_clarify: True ✅ (可以自动澄清)
      ├─ fallback_mode: False (非回退模式)
      ├─ reason_tags: ["user_dialogue_safe_valve"]
      └─ debug: {}
```

---

### 3️⃣ session_state: SessionState (会话状态)

```
该单用户会话的历史和统计：

┌─ 会话标识
│  ├─ session_key: "dm:demo_user"
│  ├─ created_at: 1771680641.5116818 (2026-02-21 13:30:41 UTC)
│  └─ last_active_at: 1771680645.015858 (2026-02-21 13:30:45 UTC)
│
├─ 处理统计
│  ├─ processed_total: 3 条观察
│  └─ error_total: 0 条错误
│
├─ 当前时间
│  └─ now: 2026-02-21 13:30:45.016357 UTC
│
└─ 会话历史 (recent_obs)
   │ 最近 20 条观察（FIFO 队列）:
   │
   ├─ [1/3] 用户消息 "你好"
   │  ├─ obs_id: affe23ed3d44484ebf2a0def72f7e8e6
   │  ├─ actor_id: demo_user
   │  ├─ text: "你好"
   │  ├─ source: text_input (用户输入)
   │  ├─ timestamp: 2026-02-21 13:30:41.460037 UTC
   │  └─ raw_event_id: "text_input:1"
   │
   ├─ [2/3] Agent 回复 "这是一个默认回复。"
   │  ├─ obs_id: 9a1ab85cee4f453a9d51f4e2b24769df
   │  ├─ actor_id: agent
   │  ├─ actor_type: system
   │  ├─ text: "这是一个默认回复。"
   │  ├─ source: agent:speaker (Agent说话)
   │  ├─ timestamp: 2026-02-21 13:30:41.512683 UTC
   │  └─ metadata: {'pool': 'chat'} (来自聊天池)
   │
   └─ [3/3] 用户消息 "很好" ← 【当前请求】
      ├─ obs_id: 3f81181db06840199d8289944c12a989
      ├─ actor_id: demo_user
      ├─ text: "很好"
      ├─ source: text_input
      ├─ timestamp: 2026-02-21 13:30:45.015357 UTC
      └─ raw_event_id: "text_input:2"
```

---

### 4️⃣ now: datetime (当前时间)

```
处理此请求时的系统时间（UTC）：

2026-02-21 13:30:45.016357 +00:00
└─ 用于：
   ├─ 计时预算检查
   ├─ 日志时间戳
   ├─ 会话超时判定
   └─ 审计追踪
```

---

### 5️⃣ gate_hint: GateHint (网关提示 - 可选)

```
gate_decision.hint 的副本，用于便捷访问：

model_tier: "low"
response_policy: "respond_now"
budget:
  ├─ budget_level: "tiny"
  ├─ time_ms: 500
  ├─ max_tokens: 256
  └─ ... (其他字段同上)
reason_tags: ["user_dialogue_safe_valve"]
debug: {}
```

---

## 💡 关键理解

### 为什么分为 5 个部分？

| 部分 | 来源 | 用途 |
|------|------|------|
| **obs** | 用户/系统 | 当前输入是什么、来自谁 |
| **gate_decision** | 安全网关 | 这个输入安全吗、需要多少资源 |
| **session_state** | 会话管理器 | 这个用户之前说过什么、会话多活跃 |
| **now** | 系统时钟 | 现在是什么时间 |
| **gate_hint** | 网关 (副本) | 快速查询预算上限 |

### 信息流

```
用户输入 "很好"
  ↓
Core 创建 Observation
  ↓
安全网关决策：是否通过？→ GateDecision + GateHint
  ↓
会话管理器提供上下文 → SessionState (历史 + 统计)
  ↓
组装 AgentRequest 发送给 Agent
```

---

## 🎯 你的 Agent 中很可能需要的信息

```python
# 在 queen.py 中，你可能会这样用：

async def handle(self, req: AgentRequest) -> AgentOutcome:
    # 1. 获取用户输入
    user_text = req.obs.payload.text  # "很好"
    user_id = req.obs.actor.actor_id   # "demo_user"
    
    # 2. 检查网关是否允许
    if req.gate_decision.action != GateAction.DELIVER:
        return AgentOutcome(emit=[...], error="Blocked by gate")
    
    # 3. 查看可用资源
    time_budget = req.gate_hint.budget.time_ms  # 500ms
    token_budget = req.gate_hint.budget.max_tokens  # 256
    can_use_tools = req.gate_hint.budget.max_tool_calls > 0  # False
    
    # 4. 查看对话历史
    conversation = [
        f"[{obs.actor.actor_type}] {obs.payload.text}"
        for obs in req.session_state.recent_obs
    ]
    # ["[user] 你好", "[system] 这是一个默认回复。", "[user] 很好"]
    
    # 5. 做出决策
    # → 决定使用哪个 pool
    # → 生成回复 (不超过 256 token)
    # → 在 500ms 内完成
```

---

## 📋 数据质量检查清单

```python
✅ 有有效的消息内容吗？
   obs.payload.text = "很好" ✓

✅ 有用户标识吗？
   req.obs.actor.actor_id = "demo_user" ✓

✅ 有会话标识吗？
   req.session_key = "dm:demo_user" ✓

✅ 网关允许处理吗？
   req.gate_decision.action = DELIVER ✓

✅ 有足够的时间预算吗？
   time_ms = 500 ✓

✅ 有足够的 token 预算吗？
   max_tokens = 256 ✓

✅ 没有质量问题吗？
   quality_flags = set() (空) ✓

✅ 有对话历史吗？
   recent_obs = [3 条观察] ✓
```

---
