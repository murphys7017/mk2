# Gate 子系统规范

## 概述

Gate（脑干门控）是一个**纯过滤和路由引擎**，不涉及智能推理。

其目的：
- 快速分类请求
- 保护系统不被过载
- 隔离不同类型的会话
- 支持运行时降级

---

## 设计原则

### 1. 确定性
Gate 的决策完全由输入和配置决定，不涉及随机或学习。

### 2. 快速
Gate 必须在毫秒级完成，不能成为系统瓶颈。

### 3. 可预测
用户可以完全理解 Gate 为什么做出某个决策（可追踪）。

### 4. 可配置
Gate 的所有规则都在 YAML 中定义，支持热更新。

### 5. 可观测
Gate 的每个决策都产生可审计的事件。

---

## 核心概念

### 场景（Scene）

Gate 首先将每个 Observation 分类为一个场景：

```python
class Scene(str, Enum):
    DIALOGUE = "dialogue"      # 多轮对话
    GROUP = "group"            # 分组对话（会议、群聊）
    SYSTEM = "system"          # 系统命令
    ALERT = "alert"            # 错误和痛觉信号
    SCHEDULE = "schedule"      # 定时任务
    WORLD_DATA = "world_data"  # 外部数据
```

**推断规则**（在 SceneInferencer 中）：

- 如果是 CONTROL / ALERT / SCHEDULE / WORLD_DATA 类型，按类型走
- 否则：
  - 如果包含群组标识（group_id）→ GROUP
  - 如果包含多轮标识（session 多于 1 条历史）→ DIALOGUE
  - 默认 → DIALOGUE

### 决策（GateAction）

Gate 的最终决策是三个之一：

```python
class GateAction(str, Enum):
    DELIVER = "deliver"  # 通过，交给 Agent 处理
    SINK = "sink"        # 接收但不处理（响应空白）
    DROP = "drop"        # 直接丢弃（无响应）
```

### 结果（GateOutcome）

Gate 返回一个完整的结果对象：

```python
@dataclass
class GateOutcome:
    decision: GateDecision           # 最终决策 + 理由
    emit: list[Observation]         # 需要生成的新 obs
    ingest: list[tuple[str, str]]   # 需要反馈给 Gate 的数据
```

---

## 7 阶段管道

Gate 按以下顺序处理每个 Observation：

### Stage 1: HardBypass（硬过滤）

**职责**：处理绝对禁止的请求（DROP）和突发信号（ALERT）。

**逻辑**：
1. 检查是否在 `drop_sessions` / `drop_actors` 列表中 → DROP
2. 检查 drop_pool 的突发状态：
   - 如果连续 DROP，达到 burst_threshold（5 次/60s）
   - 生成痛觉 ALERT
   - 激活冷却期（300s）
3. 检查是否在 `deliver_sessions` / `deliver_actors` 白名单中 → 跳过评分，直接 DELIVER
4. 否则继续

**输出**：GateAction（DELIVER / DROP）或 ALERT 信号

### Stage 2: FeatureExtractor（特征提取）

**职责**：提取文本特征以供评分。

**特征类型**：
- 文本长度
- 关键字匹配
- 实体识别（基本）
- 语言检测（可选）

**输出**：特征向量 / 特征字典

### Stage 3: Scoring（评分）

**职责**：根据规则和特征计算得分。

**规则来源**：`config/gate.yaml` 的 `rules` 部分

```yaml
rules:
  dialogue:
    weight_dialogue: 0.6           # 基础权重
    keywords_low: ["hello", "hi"]  # 低分关键字
    keywords_high: ["urgent"]      # 高分关键字
    long_text_len: 500             # 长文本阈值
  group:
    weight_group: 0.7
  system:
    weight_system: 1.0
  alert:
    weight_alert: 0.0  # ALERT 总是通过
```

**算法**（简单例子）：
```
base_score = scene_weight

if any keyword in [keywords_high]:
    score = base_score * 1.5
elif any keyword in [keywords_low]:
    score = base_score * 0.5
else:
    score = base_score

if len(text) > long_text_len:
    score *= 1.2  # 长文本加分

final_score = min(max(score, 0.0), 1.0)  # 限制到 [0, 1]
```

**输出**：得分（0.0 到 1.0）

### Stage 4: Dedup（去重）

**职责**：基于指纹过滤重复请求。

**指纹构造**：
- 计算文本的 MD5 哈希（对话、分组）
- 每个场景有独立的 dedup_window（如 30 秒）

**例外**：
- ALERT 永远不去重（痛觉信号必须聚合）
- SCHEDULE / WORLD_DATA 不需要去重

**输出**：SINK（如果重复）或继续

### Stage 5: PolicyMapper（策略映射）

**职责**：根据得分和策略决定是否通过。

**规则**：
```yaml
scene_policies:
  dialogue:
    threshold: 0.5       # 得分 ≥ 0.5 才通过
    default_action: DELIVER
  alert:
    threshold: 0.0       # ALERT 总是通过
    default_action: DELIVER
```

**逻辑**：
```
score >= scene_policy.threshold → decision = DELIVER
else → decision = SINK
```

如果有 `emergency_mode` 覆盖：
```
emergency_mode == true → 所有场景 threshold 提高 50%（更严格）
```

**输出**：GateAction（DELIVER 或 SINK）

### Stage 6: Finalize（最终化）

**职责**：补全决策信息，准备返回。

**操作**：
- 记录决策理由（为什么 DELIVER / SINK / DROP）
- 记录得分和规则命中
- 生成可观测事件（可选）

**输出**：完整的 GateDecision

### Stage 7: Outcome Assembly（结果组装）

**职责**：整合所有反馈和新生成的观察。

**内容**：
```python
outcome.decision = ...           # 最终决策
outcome.emit = [alert, ...]      # 从 HardBypass 生成的痛觉信号
outcome.ingest = [(...), ...]    # 反馈给 drop_pool 的数据
```

**输出**：完整的 GateOutcome

---

## 配置规范

### config/gate.yaml 结构

```yaml
version: "1.0"

# 场景策略
scene_policies:
  dialogue:
    threshold: 0.5
    default_action: DELIVER
    dedup_window: 30s
  group:
    threshold: 0.6
    default_action: DELIVER
    dedup_window: 30s
  alert:
    threshold: 0.0
    default_action: DELIVER
  schedule:
    threshold: 0.0
    default_action: DELIVER
  world_data:
    threshold: 0.0
    default_action: DELIVER

# 评分规则
rules:
  dialogue:
    weight_dialogue: 0.6
    keywords_low: ["hello", "hi", "thanks"]
    keywords_high: ["urgent", "critical", "asap"]
    long_text_len: 500
  group:
    weight_group: 0.7
    keywords_high: ["meeting", "important"]
  system:
    weight_system: 1.0
  alert:
    weight_alert: 0.0

# DROP 突发规则
drop_escalation:
  burst_threshold: 5           # 连续 5 个 DROP
  burst_window: 60s            # 在 60 秒内
  cooldown_duration: 300s      # 触发 300 秒冷却
  overload_threshold: 0.5      # 如果 DROP 比例 > 50%

# 运行时覆盖
overrides:
  emergency_mode: false        # 提高所有阈值 50%
  force_low_model: false       # 强制使用低成本模型（Agent 侧）
  drop_sessions: []            # 黑名单 session_id
  deliver_sessions: []         # 白名单 session_id
  drop_actors: []              # 黑名单 actor_id
  deliver_actors: []           # 白名单 actor_id
```

### 热更新格式

在运行时通过代码更新 overrides：

```python
# 激活 emergency_mode
provider.update_overrides(emergency_mode=True)

# 或多个同时更新
provider.update_overrides(
    emergency_mode=True,
    force_low_model=True,
    drop_sessions=["bad_session_123"]
)

# 或撤销
provider.update_overrides(emergency_mode=False)
```

---

## 与 Agent 的边界

### Gate 不做的事

❌ 内容理解（"这条消息讲什么"）
❌ 语义相似度（"这和那个消息重复吗"） 
❌ 意图判断（"用户想要什么"）
❌ 历史上下文（Agent 负责）
❌ 响应生成（Agent 负责）

### Gate 只做的事

✅ 速度检查（过滤垃圾、spam）
✅ 过载保护（DROP / SINK）
✅ 基础去重（指纹级别）
✅ 路由（哪个 session，哪个优先级）
✅ 降级（emergency 时提高标准）

---

## 与 System Reflex 的关系

Gate 和 SystemReflex 形成一个反馈闭环：

```
Gate 检测到 DROP 突发
  ↓
生成 ALERT（痛觉）
  ↓
SystemReflex 接收 ALERT
  ↓
评估：是否触发 emergency_mode
  ↓
调用 provider.update_overrides(emergency_mode=True)
  ↓
Gate 在下一个循环中采用新的阈值
```

**关键约束**：
- Gate 不直接调用 SystemReflex
- SystemReflex 不直接修改 Gate 代码
- 通信纽带是 Observation + GateConfigProvider

---

## 可观测性

### 关键指标

Gate 应记录或发出以下信息：

1. **决策分布**
   ```
   决策 = DELIVER: 80%
   决策 = SINK: 15%
   决策 = DROP: 5%
   ```

2. **得分分布**
   ```
   场景 = dialogue, 平均得分 = 0.65
   场景 = group, 平均得分 = 0.72
   ```

3. **去重效果**
   ```
   总观察数 = 1000
   去重被吸收 = 150
   ```

4. **突发信号**
   ```
   场景 = dialogue, burst 触发次数 = 3
   每次影响会话数 = 1-5
   ```

### 事件日志

Gate 可在关键决策点生成事件：

```python
if outcome.decision.action == GateAction.DROP:
    log_event("gate.drop", {
        "scene": obs.scene,
        "reason": outcome.decision.reason,
        "actor": obs.actor_id,
        "timestamp": now
    })

if outcome.emit:
    for alert in outcome.emit:
        log_event("gate.pain_generated", {
            "pain_key": extract_pain_key(alert),
            "severity": alert.severity,
            "timestamp": now
        })
```

---

## 测试策略

### 单元测试

1. **SceneInferencer**：确保场景分类准确
2. **Scoring**：验证各类型规则的评分逻辑
3. **PolicyMapper**：确保阈值判决正确
4. **Dedup**：验证指纹去重和 ALERT 豁免
5. **HardBypass**：验证白黑名单和突发检测

### 集成测试

1. **Gate MVP**：端到端流程
2. **Gate + Config**：YAML 加载和热更新
3. **Gate + Worker**：outcome 执行
4. **Gate + SystemReflex**：痛觉反馈

### 压力测试

- 高频率请求（验证过载保护）
- 大量 DROP（验证突发检测）
- 配置热更新（验证一致性）

---

## 常见问题

### Q: 为什么 ALERT 不去重？

**A**: 痛觉信号代表真实的系统问题，每一个都需要被计入。如果去重，会隐藏错误频率。

### Q: emergency_mode 会永久激活吗？

**A**: 不会。emergency_mode 由 SystemReflex 根据痛觉信号自动管理，通常在 5-10 分钟后自动关闭。

### Q: 能否在 Gate 中运行 LLM？

**A**: 不建议。Gate 的目标是毫秒级响应。如果需要语义理解，应放到 Agent 层。

### Q: overrides 可以直接修改文件吗？

**A**: 可以。GateConfigProvider 会定期检查 YAML 文件的修改时间，自动重新加载。

### Q: 如何调试 Gate 决策？

**A**: 启用日志级别 DEBUG，Gate 会记录每个阶段的详细信息。或在测试中直接检查 GateOutcome。

