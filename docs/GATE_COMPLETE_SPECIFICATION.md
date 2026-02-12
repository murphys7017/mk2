# Gate 模块完整设计规范（用于重构与策略修订）

> 本文基于现有代码与配置推断，适用于 Gate 的语义/策略改造建议。

---

## 1. Gate 的目标与职责边界

### 1.1 Gate 的职责

Gate 是 Core 中的**决策层**，位于 SessionRouter 和 Agent 之间：

```
Adapter → AsyncInputBus → SessionRouter(multi-inbox) → [GATE] → SessionState.recent_obs
                                                         ↓
                                                  Agent（可选）
```

Gate 的核心职责：
- **信号分类**（Scene inference）：识别输入是对话、系统、告警、工具调用等
- **信号评分**（Scoring）：基于文本特征、关键词等生成 [0.0, 1.0] 的相关性评分
- **策略决策**（Policy Mapping）：根据评分、场景、优先级规则决定 action（DELIVER / SINK / DROP）
- **紧急保护**（Hard Bypass）：系统过载时快速 DROP，防止级联故障
- **可观测性**：通过 emit/ingest 和日志支持链路追踪

### 1.2 Gate 不负责的工作

- **LLM 调用**：Agent 负责
- **Session 生命周期管理**：Core 和 SessionRouter 负责
- **Adapter 管理**：Core 负责
- **输入格式转换**：SessionRouter 负责
- **Session state 存储**：SessionState 负责
- **告警聚合**：SystemReflex 负责

### 1.3 与其他模块的边界

| 模块 | 边界 | 交互方式 |
|------|------|--------|
| **Core** | Gate 被初始化为 `core.gate`，在 `_session_loop` 中被调用。Core 控制 Gate 的启动和配置重载 | `outcome = gate.handle(obs, ctx)` |
| **SessionState** | Gate 通过 `ctx.session_state` 读取历史（recent_obs）和统计、但不修改。SessionState 由 SessionWorker 维护 | Context 指针传递 |
| **SessionRouter** | Gate 接收来自 router 分发的 Observation。不与 router 反向通信 | 单向数据流 |
| **Agent** | Gate 的 DELIVER 决策决定了是否调用 Agent。Agent 不能改变 Gate 的决策 | `if decision.action == DELIVER: await agent.handle(obs, decision)` |
| **SystemReflex** | Gate 可以 emit 痛觉告警（AlertPayload），Reflex 在 system session 中进行处理 | emit → bus → system session |

---

## 2. Gate 的输入与上下文

### 2.1 输入 Observation 的关键字段

Gate 接收的 `Observation` 对象的关键字段：

```python
obs.obs_type       # ObservationType: MESSAGE | ALERT | CONTROL | SCHEDULE | SYSTEM
obs.source_name    # str: 来源标签（如 "text_input_adapter", "core:fanout"）
obs.source_kind    # SourceKind: EXTERNAL | INTERNAL | SYSTEM
obs.session_key    # str: 会话标识（如 "dm:user123", "system"）
obs.actor          # Actor: actor_id, actor_type ("user"/"agent"/"system"), display_name
obs.payload        # Union[MessagePayload, AlertPayload, ...]
```

**关键观察**：
- `obs.actor.actor_type == "agent"` 时，必须 **防止死循环**（_handle_user_observation 中已实现）
- `obs.payload` 的类型决定了如何提取文本内容（MessagePayload 有 text，AlertPayload 有 alert_type）
- `obs.session_key == system_session_key` 时走系统处理路径

### 2.2 GateContext 的关键字段

Gate 处理时的上下文（由 SessionWorker 构造）：

```python
ctx.now                    # datetime: 当前时间（UTC）
ctx.config                 # GateConfig: 当前配置快照
ctx.system_session_key     # str: 系统会话 key（通常 "system"）
ctx.metrics                # GateMetrics: 统计对象
ctx.session_state          # SessionState: 该会话的状态对象
  └─ session_state.recent_obs       # List[Observation]: 最近 N 条消息
  └─ session_state.processed_total  # int: 处理总数
  └─ session_state.idle_seconds()   # Optional[float]: 空闲时间
ctx.system_health          # Optional[Dict]: {"overload": bool}
ctx.trace                  # Optional[Callable]: 调试回调
```

**重要**：Gate 从 SessionState 中读取历史，但不修改。SessionWorker 是修改方。

### 2.3 Scene 的推断逻辑

Gate 通过 `SceneInferencer` 推断输入的场景类型：

```python
class Scene(str, Enum):
    DIALOGUE = "dialogue"       # 用户消息（单聊）
    GROUP = "group"             # 群组消息
    SYSTEM = "system"           # 系统事件
    TOOL_CALL = "tool_call"     # 工具调用请求
    TOOL_RESULT = "tool_result" # 工具执行结果
    ALERT = "alert"             # 痛觉告警
    UNKNOWN = "unknown"         # 未知
```

**推断规则**（由代码实现，SceneInferencer 中）：
- `obs.obs_type == ALERT` → Scene.ALERT
- `obs.session_key == system_session_key` → Scene.SYSTEM
- `obs.obs_type == MESSAGE` 且 `obs.actor.actor_type == "user"` → DIALOGUE（若 session_key 非 system）
- 其他 MESSAGE → GROUP（多人场景）
- `obs.source_name` 包含 "tool" → TOOL_CALL / TOOL_RESULT
- 否则 → UNKNOWN

---

## 3. Gate 的决策产物（GateOutcome）

### 3.1 GateDecision 的字段与语义

```python
@dataclass
class GateDecision:
    action: GateAction              # 核心决策：DROP / SINK / DELIVER
    scene: Scene                    # 推断的场景
    session_key: str                # 目标会话
    target_worker: Optional[str]    # 若为 SYSTEM，指向 system_session_key
    model_tier: Optional[str]       # 优先级："low" / "high" / None
    response_policy: Optional[str]  # 响应策略："respond_now" / "defer" / None
    tool_policy: Optional[Dict]     # 工具相关配置
    score: float                    # 评分 [0.0, 1.0]
    reasons: List[str]              # 决策理由（最多 max_reasons 条）
    tags: Dict[str, str]            # 标签（如 "drop_burst": "true"）
    fingerprint: Optional[str]      # 去重指纹
```

### 3.2 GateAction 的枚举值与语义

| Action | 值 | 含义 | 下游处理 | 何时使用 |
|--------|----|------|--------|---------|
| **DROP** | "drop" | 硬丢弃，不保存、不回复 | 进 drop_pool；ServiceWorker 不调用 Agent | 系统过载、空消息、恶意输入 |
| **SINK** | "sink" | 入池保存，不主动回复 | 进 sink_pool（或 tool_pool）；ServiceWorker 继续但不调用 Agent | 评分低、群消息、工具结果 |
| **DELIVER** | "deliver" | 直接投递，调用 Agent 回复 | 不入池；ServiceWorker 调用 Agent | 评分高、明确请求、告警 |

### 3.3 GateOutcome 的字段与处理

```python
@dataclass
class GateOutcome:
    decision: GateDecision          # 上述决策
    emit: List[Observation] = []    # **要发送到 bus 的观察**
    ingest: List[Observation] = []  # **要存储到池中的观察**
```

**emit 的含义**：
- 痛觉告警：当检测到过载或 drop burst 时，emit 包含 AlertPayload（`make_pain_alert()`）
- Core 会通过 `bus.publish_nowait(emit_obs)` 将其发送回输入总线（通常供 system session 处理）

**ingest 的含义**：
- DROP 的消息：`ingest = [obs]`，进 drop_pool
- SINK 的消息：`ingest = [obs]`，进 sink_pool（或 tool_pool）
- DELIVER 的消息：`ingest = []`（不入池）
- Core 通过 `gate.ingest(obs, decision)` 后续处理

---

## 4. Gate 的决策流程（按执行顺序）

Gate 通过 `DefaultGatePipeline.run(obs, ctx, wip)` 执行，流程如下：

### 4.1 阶段 1：Scene Inferencer（场景推断）

**类**：`SceneInferencer`  
**输入**：`obs` 和 `ctx`  
**输出**：`wip.scene`

操作：
```
if obs.obs_type == ALERT:
    scene = ALERT
elif obs.session_key == ctx.system_session_key:
    scene = SYSTEM
elif obs.obs_type == MESSAGE and obs.actor.actor_type == "user":
    scene = DIALOGUE
elif obs.source_name contains "tool":
    scene = TOOL_CALL / TOOL_RESULT
else:
    scene = UNKNOWN
```

### 4.2 阶段 2：Hard Bypass（硬门控与过载保护）

**类**：`HardBypass`  
**职责**：快速拦截明显的不合理输入和系统故障

操作流程：

1. **系统过载检查**
   ```
   if ctx.system_health.get("overload"):
       wip.action_hint = DROP
       emit pain_alert("Gate overload detected")
       return  # 立即返回，跳过后续 pipeline
   ```

2. **DROP 者重置**（允许 ALERT 通过，重置计数）
   ```
   if obs.obs_type == ALERT:
       _monitor.reset_consecutive()
   ```

3. **空消息 DROP**
   ```
   if obs.obs_type == MESSAGE and not (payload.text.strip() or attachments):
       wip.action_hint = DROP
   ```

4. **DROP 监控与升级**（滑窗频率）
   ```
   if wip.action_hint == DROP:
       _monitor.record_drop()  # 计时归档
       if len(timestamps_in_window) >= burst_count_threshold:
           wip.tags["drop_burst"] = "true"
           emit pain_alert("Drop burst detected")
   ```

**重要参数**（来自 gate.yaml）：
```yaml
drop_escalation:
  burst_window_sec: 10          # 滑窗大小
  burst_count_threshold: 20     # DROP 次数超过该值时升级
  consecutive_threshold: 8      # 连续 DROP 超过该值时升级
  cooldown_suggest_sec: 15      # 建议冷却时间
```

### 4.3 阶段 3：Feature Extractor（特征提取）

**类**：`FeatureExtractor`  
**职责**：从 Observation 和 SessionState 中提取得分特征

提取内容：
```python
wip.features = {
    "actor_id": obs.actor.actor_id,
    "text": obs.payload.text if MESSAGE else None,
    "text_len": len(text),
    "has_mention": "@bot" in text,
    "has_question": "?" in text,
    "has_bot_mention": "@bot_name" in text,
    "recent_obs_count": len(ctx.session_state.recent_obs),
    # ... 其他特征
}
```

### 4.4 阶段 4：Scoring Stage（信号评分）

**类**：`ScoringStage`  
**输入**：`wip.scene` 和 `wip.features`  
**输出**：`wip.score` [0.0, 1.0]

评分规则由 `GateConfig.rules` 定义（见 gate.yaml）：

```python
if scene == DIALOGUE:
    score = 0.10                    # base weight
    if has_mention:  score += 0.40
    if has_question: score += 0.15
    if text_len >= 300: score += 0.10
    for keyword in ["urgent", "error", "help"]:
        if keyword in text: score += keyword_weight
    
elif scene == GROUP:
    score = 0.05                    # base weight
    if has_bot_mention: score += 0.60
    if actor_id in whitelist: score += 0.25
    
elif scene == ALERT:
    score = 0.6
    
elif scene == SYSTEM:
    score = 0.0
    
elif scene == TOOL_CALL:
    score = 0.7
    
elif scene == TOOL_RESULT:
    score = 0.5

# 文本长度加权
score += min(text_len / 200.0, 0.2)

# 上下限
wip.score = max(0.0, min(score, 1.0))
```

**关键配置**（gate.yaml）：
```yaml
rules:
  dialogue:
    weights:
      base: 0.10
      mention: 0.40
      question_mark: 0.15
      long_text: 0.10
    keywords:
      urgent: 0.30
      error: 0.25
      help: 0.15
    long_text_len: 300
```

### 4.5 阶段 5：Deduplicator（可选去重）

**类**：`Deduplicator`  
**职责**：检测重复请求并标记（通过 fingerprint）

（实现略）允许配置 dedup_window_sec 跳过最近 N 秒的相同消息。

### 4.6 阶段 6：Policy Mapper（策略映射与覆盖）

**类**：`PolicyMapper`  
**职责**：根据 score、scene 和 overrides 决定最终 action

流程（**优先级从高到低**）：

```
1. emergency_mode (覆盖最高级)
   if overrides.emergency_mode:
       action = SINK
       model_tier = "low"
       
2. drop_sessions (强制 DROP 指定会话)
   if obs.session_key in overrides.drop_sessions:
       action = DROP
       
3. drop_actors (强制 DROP 指定用户)
   if obs.actor.actor_id in overrides.drop_actors:
       action = DROP
       
4. deliver_sessions (强制 DELIVER 指定会话)
   if obs.session_key in overrides.deliver_sessions:
       action = DELIVER
       model_tier = policy.default_model_tier
       
5. deliver_actors (强制 DELIVER 指定用户)
   if obs.actor.actor_id in overrides.deliver_actors:
       action = DELIVER
       
6. hard_bypass action_hint (来自 HardBypass 的 DROP 标记)
   if wip.action_hint == DROP:
       action = DROP
       
7. score-based policy (标准策略)
   policy = ctx.config.scene_policy(scene)
   if wip.score >= policy.deliver_threshold:
       action = DELIVER
   elif wip.score >= policy.sink_threshold:
       action = SINK
   else:
       action = policy.default_action
       
8. force_low_model (仅在 DELIVER 时生效)
   if overrides.force_low_model and action == DELIVER:
       model_tier = "low"
```

**关键配置**（gate.yaml）：
```yaml
scene_policies:
  dialogue:
    deliver_threshold: 0.75        # ≥此阈值就 DELIVER
    sink_threshold: 0.20           # ≥此阈值（但 <deliver）就 SINK
    default_action: "sink"         # <sink_threshold 时的默认
    default_model_tier: "low"
    default_response_policy: "respond_now"

overrides:
  emergency_mode: false
  force_low_model: false
  drop_sessions: []
  deliver_sessions: ["demo"]       # 演示用：强制 DELIVER
  drop_actors: []
  deliver_actors: []
```

### 4.7 阶段 7：Finalize Stage（决策收敛）

**类**：`FinalizeStage`  
**职责**：将 `wip` 转换为 `GateDecision` 和 `GateOutcome`，更新 metrics

操作：
```python
decision = GateDecision(
    action=wip.action_hint or SINK,
    scene=wip.scene or UNKNOWN,
    session_key=obs.session_key,
    model_tier=wip.model_tier,
    response_policy=wip.response_policy,
    score=wip.score,
    reasons=wip.reasons[:max_reasons],
    tags=wip.tags,
)

outcome = GateOutcome(
    decision=decision,
    emit=wip.emit,       # 痛觉告警
    ingest=wip.ingest,   # 入池观察（由 DefaultGate.handle 补充）
)

# 更新 metrics
ctx.metrics.processed_total += 1
ctx.metrics.inc_scene(scene)
ctx.metrics.inc_action(action)
```

---

## 5. Gate 与"用户体验"的关系

### 5.1 用户 MESSAGE 何时被 SINK

用户 MESSAGE（scene=DIALOGUE）会在以下条件**之一**被 SINK：

| 条件 | 值 | 优先级 | 备注 |
|------|-----|-------|------|
| 评分过低 | score < sink_threshold（0.20）| 标准 | 这是最常见的 SINK 原因 |
| 无提及 & 无问好 & 短文本 | base=0.10 < 0.20 | 标准 | 例：纯问候 "hi" |
| delivery_override 未触发 | overrides.deliver_sessions 不包含 session_key | 覆盖 | 除非显式白名单，否则 SINK |
| 非紧急关键词 | 无 "urgent", "error", "help" | 标准 | 无关键词贡献额外分数 |
| group 场景 & 非 mention & 非 whitelist | base=0.05 + other<1.5 | 标准 | 群消息更容易 SINK |

### 5.2 SINK 的产品语义

当用户 MESSAGE 被 SINK：

```
用户消息 → Gate.SINK → ingest 到 sink_pool
          ↓
    SessionWorker 继续处理（不返回错误）
          ↓
    Agent 不被调用（因为 decision.action != DELIVER）
          ↓
    **系统没有立即回复**
          ↓
    消息存储在 sink_pool，供后续 reflex/batch 处理
```

**经验**：
- SINK 意图是"**存档但不即时回复**"（类似邮件系统的"存档"）
- 这可能造成用户不知道系统收到消息的**"沉默黑洞"**问题
- 配置中 deliver_sessions=["demo"] 是演示用例，强制 demo 会话的消息都 DELIVER（全部回复）

### 5.3 是否存在"用户消息但系统无回复"的路径

**存在，具体路径如下**：

```
情形 1：评分低导致 SINK（最常见）
  - 用户发 "hi"（无提及、无问题、短）
  - score = 0.10 + 0.02(text_len) = 0.12 < 0.20 (sink_threshold)
  - action = SINK（default_action）
  - SessionWorker 写日志但不调用 Agent
  - **用户无回复**

情形 2：硬 DROP（系统过载）
  - 系统 overload=true
  - wip.action_hint = DROP
  - action = DROP
  - 消息进 drop_pool，完全丢弃
  - **用户无回复，消息也无存档**

情形 3：overrides 强制 DROP
  - obs.session_key in overrides.drop_sessions
  - action = DROP
  - **用户无回复**

情形 4：群消息评分低
  - scene = GROUP, 无 @mention
  - score = 0.05 < 0.20 (group sink_threshold 0.30)
  - action = SINK or DROP
  - **群内无人应答**
```

**触发条件总结**：
- 评分 < sink_threshold（通常 0.20-0.30）
- OR 硬 DROP（系统过载或恶意输入）
- OR 明确 overrides 禁止
- 且 **无 deliver_sessions / deliver_actors 覆盖**

---

## 6. 可观测性与日志

### 6.1 Gate 打印/记录的关键字段

Gate 在 Core._session_loop 中打印了以下 JSON 日志：

```
[WORKER:IN] {
    "obs_id": "...",
    "obs_type": "MESSAGE",
    "session_key": "dm:user123",
    "actor_id": "user1",
    "timestamp": "2026-02-13T..."
}

[GATE:CTX] {
    "config_version": 1,
    "session_key": "dm:user123",
    "state_processed": 5
}

[GATE:OUT] {
    "action": "deliver",
    "emit_count": 0,
    "ingest_count": 0
}

[DELIVER] {
    "obs_id": "...",
    "obs_type": "MESSAGE",
    "session_key": "dm:user123",
    "action": "deliver"
}
```

### 6.2 根据日志判断 SINK/DELIVER/DROP 的原因

查看 [GATE:OUT] 的 action 字段和 SessionWorker 的日志其他字段：

```
action="sink":
  - 查看 logs 中的 score 和 threshold
  - 若 score < sink_threshold，则标准分数评估
  - 若有 "override" 标签，则查看 gate.yaml 的 overrides
  
action="deliver":
  - 若 reasons 包含 "override=deliver_session"，则被白名单覆盖
  - 否则 score >= deliver_threshold（通常 0.70-0.75）
  
action="drop":
  - 若 tags["drop_burst"]="true"，则是 hard_bypass 的 drop burst 检测
  - 若 reasons 包含 "empty_content"，则空消息被丢弃
  - 若 reasons 包含 "system_overload"，则系统过载
  - 若 reasons 包含 "override=drop_session"，则被禁用列表覆盖
```

**完整日志示例**（从 core.py 看）：

```json
{
  "stage": "GATE:OUT",
  "decision": {
    "action": "sink",
    "scene": "dialogue",
    "score": 0.12,
    "reasons": ["base", "text_len"],
    "tags": {}
  }
}
```

### 6.3 GateMetrics 的统计项

```python
class GateMetrics:
    processed_total: int = 0
    dropped_total: int = 0
    sunk_total: int = 0
    delivered_total: int = 0
    
    scene_counts: Dict[str, int] = {}     # 按 scene 统计
    action_counts: Dict[str, int] = {}    # 按 action 统计
    
    # 可扩展用于
    # - 告警计数
    # - 响应时间
    # - 错误计数
```

---

## 7. 风险点与改造切入点

### 7.1 "沉默黑洞"问题（用户消息被 SINK 且无回复）

**根本原因**：
- SINK 的设计初衷是"存档不回复"
- 但用户在本地看不到 sink_pool，无法感知消息被接收
- 长期导致用户体验差（感觉系统"死掉了"）

**风险等级**：🔴 **高**（严重影响用户信任）

**现有缓解**：
- deliver_sessions 白名单可以强制某些会话全部 DELIVER（见 gate.yaml 中 demo）
- 但默认配置下普通用户会经历 SINK（评分低）

**改造建议**：
```
Option A（UX 安全阀）：
  改变 DIALOGUE 的默认策略
  - deliver_threshold: 0.75 → 0.50
  - default_action: "sink" → "deliver"
  - 这样短消息也会被 DELIVER，用户可以看到回复
  - 代价：Agent 调用频率增加 2-3 倍

Option B（被动回复）：
  SINK 时自动 emit 一个 "received, processing..." 的系统提示
  - 用户看到被接收的信号
  - 不需要立即调用 Agent

Option C（分级 SINK）：
  区分 SINK_SILENT vs SINK_WITH_ACK
  - SINK_WITH_ACK：发送确认但不深度处理
  - 需要改 GateAction 枚举
  
推荐：Option B（低成本、见效快）
```

### 7.2 "过载保护"的有效性与失效场景

**现有机制**：
- Hard Bypass 中的 `drop_escalation` 参数（burst_window_sec, burst_count_threshold）
- 当 DROP 频率超过 burst_count_threshold 时升级为 Alert

**潜在失效场景**：
```
场景 1：短期突发流量（应该被保护）
  ✓ 有效：drop_count在 10 秒内达到 20
  
场景 2：缓慢渗漏（每秒 5 个 DROP）
  ✗ 失效：不会触发 burst_count_threshold
  ✓ 但 consecutive_threshold=8 可能有帮助
  
场景 3：Agent 响应超时（不是 Gate 过载）
  ✗ 完全失效：Gate 本身不过载，问题在下游
```

**改造建议**：
```
1. 增加基于时间的监控（非仅计数）
   - sliding_window_qps: float = 10  # 每秒最多 N 条消息
   - 若 qps > threshold，触发速率限制而非完全 DROP
   
2. 区分 drop 的原因
   - gate_drop_empty: 空消息 DROP（不用限制）
   - gate_drop_overload: 过载 DROP（需要反压）
   
3. 与 Nociception 联动
   - 系统收到 drop_burst alert 后自动降级
   - core 禁用部分 adapter（如 timer_tick）
```

### 7.3 Agent 的 InfoPlan → Evidence → Answer 的 Gate 信号

**当前情况**：
- Gate 只输出 `model_tier` 和 `response_policy`
- Agent 读取这些字段来决定使用哪个 LLM

**改造建议**（为未来 Agent pipeline 准备）：

Gate 应该在 `GateDecision` 中增加以下字段：

```python
@dataclass
class GateDecision:
    # ... 现有字段 ...
    
    # Agent Pipeline 相关信号
    info_plan_budget: Dict[str, Any] = field(default_factory=dict)
    # 例：{"time_ms": 2000, "kb_tokens": 100, "memory_depth": 10}
    # - time_ms: Agent 允许花多久（低分数消息用 500ms，高分数 3000ms）
    # - kb_tokens: 检索知识库的 token 预算
    # - memory_depth: 允许读多少条历史
    
    evidence_sources: List[str] = field(default_factory=list)
    # 例：["time", "memory", "kb"]
    # 根据 signal 强度决定需要哪些证据
    
    confidence_threshold: float = 0.5
    # 若分数 < 此阈值，要求 Agent 的置信度更高
```

**改造触发点**：
```python
# 在 ScoringStage 或 PolicyMapper 中
if scene == DIALOGUE and score >= 0.7:
    decision.info_plan_budget = {"time_ms": 3000, "kb_tokens": 200}
    decision.evidence_sources = ["time", "kb", "memory"]
    decision.confidence_threshold = 0.3
    
elif scene == GROUP and score < 0.3:
    decision.info_plan_budget = {"time_ms": 500}
    decision.evidence_sources = []
    decision.confidence_threshold = 0.8
```

---

## 8. 关键配置点与入手指南

### 8.1 快速调参指南

| 目标 | 配置项 | 改动 | 预期效果 |
|------|--------|------|--------|
| 增加 DELIVER 率（更多回复） | deliver_threshold | 0.75 → 0.60 | 评分低的消息也会被回复 |
| 减少 DELIVER（省 Agent 成本） | deliver_threshold | 0.75 → 0.85 | 只有高相关性才回复 |
| 保护群聊（减少群消息处理） | group.default_action | "sink" → "drop" + raise sample_rate | 群消息大幅降采样 |
| 紧急模式（停止所有处理） | emergency_mode | false → true | 所有消息 SINK，无 DELIVER |
| 强制回复特定会话 | deliver_sessions | [] → ["dm:vip_user"] | VIP 用户消息全部回复 |
| 快速检测系统过载 | burst_count_threshold | 20 → 10 | 更敏感的 DROP burst 检测 |

### 8.2 改造顺序建议

```
Phase 1：修复沉默黑洞（2-3 days）
  → 实现 Option B（SINK_WITH_ACK）
  → 改动：Gate action 枚举 + emit logic
  
Phase 2：精细分级（1 week）
  → 增加 info_plan_budget / evidence_sources
  → 改动：GateDecision 字段 + pipeline scoring/policy
  
Phase 3：Nociception 联动（1 week）
  → Gate 监听 drop_burst alert
  → Core 自适应禁用慢 adapter
  → 改动：Core 和 Gate 的反馈环路
  
Phase 4：可观测性增强（3 days）
  → 增加 trace 回调输出详细的 pipeline 步骤
  → 支持按 session 的统计和告警
```

---

## 9. 总结与快速参考

### 9.1 Gate 的"三层"决策

| 层 | 机制 | 类 | 可配置性 |
|----|------|-----|--------|
| **第 1 层：硬门控** | 系统过载 → DROP | HardBypass | 参数：burst_window_sec, burst_count_threshold |
| **第 2 层：信号评分** | 文本 + 场景 → score | ScoringStage | 参数：rules.dialogue/group/system.weights/keywords |
| **第 3 层：策略映射** | score + overrides → action | PolicyMapper | 参数：deliver_threshold, sink_threshold, overrides |

### 9.2 最常见的改造需求

```
"用户消息为什么没有回复？"
  → 查 Gate 的 score（通常 < 0.20）
  → 调高权重（dialogue.weights.base / mention / question_mark）
  → 或降低 deliver_threshold

"系统为什么在处理期间没有反馈？"
  → Gate 将 SINK 改为 emit "received" alert
  → 或改为 DELIVER（但代价是 Agent 成本）

"系统过载时消息堆积怎么办？"
  → Hard Bypass 的 burst_count_threshold 需要调小
  → 或引入速率限制（见 7.2 改造建议）
  
"群聊消息太多，想消音？"
  → 改 group.default_action = "drop"
  → 或提高 sample_rate 的阈值
```

---

**本文档版本**：1.0（基于 mk2 项目当前代码）  
**更新日期**：2026-02-13  
**适用范围**：Gate 语义重构、策略微调、Agent 集成规划
