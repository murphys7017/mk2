# System Reflex 自调节系统规范

## 概述

System Reflex（系统自主神经）是一个**自我保护和自我调节**的闭环系统。

其目的：
- 聚合系统痛觉信号（错误、过载）
- 自动激活保护机制（emergency_mode）
- 接收 Agent 的调节建议
- 安全地应用或撤销调节

---

## 设计理念

### 生物学比喻

```
痛觉神经元         →  ALERT Observation
脊髓反射           →  Self-triggered emergency_mode
自律神经中枢       →  SystemReflexController
TTL（时限）        →  自动恢复机制
```

### 核心原则

1. **自主**：无需 Agent 干预，痛觉信号自动触发保护
2. **安全**：Agent 建议必须经过白名单+TTL 检查
3. **可观测**：所有状态变化产生事件
4. **自恢复**：所有临时调节都有超时自动撤销
5. **可控**：人类可以随时干预（修改 overrides）

---

## 架构设计

### 三个主要组件

#### 1. 痛觉系统（nociception.py）

**职责**：生成和分析痛觉信号

```python
def make_pain_alert(
    source_kind: str,           # "adapter", "gate", "agent"
    source_id: str,             # "a1", "dialogue", "llm_service"
    severity: str,              # "critical", "warning", "info"
    message: str
) -> Observation:
    """
    生成标准的痛觉 ALERT.
    示例：
    - source_kind="adapter", source_id="a1", severity="critical"
      → 意味着 adapter a1 出现严重错误
    """
```

**痛觉信号示例**：
```
ALERT {
    obs_type: ALERT,
    severity: "critical",
    payload: AlertPayload {
        title: "Adapter error burst",
        detail: "adapter:a1 failed 5 times in 60s",
        source_kind: "adapter",
        source_id: "a1",
        timestamp: now
    }
}
```

**提取痛觉信息**：
```python
def extract_pain_key(alert: Observation) -> str:
    """
    从 ALERT 中提取痛觉关键字（"adapter:a1" 格式）
    """
```

#### 2. 反射控制器（system_reflex/controller.py）

**职责**：评估痛觉信号，做出自调节决策

```python
class SystemReflexController:
    """
    处理系统的自保护反射和 Agent 建议采纳
    """
    
    def handle_observation(
        self, 
        obs: Observation, 
        now: float
    ) -> list[Observation]:
        """
        处理一个观察，返回可能生成的新观察。
        支持三种观察类型：
        - ALERT（痛觉）
        - CONTROL(tuning_suggestion)（Agent 建议）
        - CONTROL(system_mode_changed)（用于内部跟踪）
        """
```

**处理流程**：

```
ALERT 观察
  ↓ (包含 pain_key)
解析痛觉来源和严重程度
  ↓
调用 _evaluate_pain_signal()
  ↓
  ├─ 统计同类痛觉（burst 检测）
  ├─ 评估是否达到激活阈值
  └─ 如果激活，决定调节行为
  ↓
调用 provider.update_overrides()
  ↓
emit CONTROL(system_mode_changed)
  ↓
记录状态变化到 suggestion_state
```

#### 3. 配置提供者（config_provider.py）

**职责**：管理 GateConfig，提供快照，应用更新

```python
class GateConfigProvider:
    """
    Gate 配置的唯一持有者和修改器
    """
    
    def snapshot(self) -> GateConfig:
        """
        返回当前配置的不可变快照
        线程安全（GIL 保护）
        """
    
    def update_overrides(self, **kwargs) -> GateConfig:
        """
        更新 overrides，返回新的配置
        实现方式：创建新 config，原子替换 _ref
        """
```

---

## 痛觉聚合流程

### 1. 痛觉生成

Gate 或 Adapter 检测到错误：

```python
# 在 src/core.py 中
if event_type == "adapter_error":
    alert = make_pain_alert(
        source_kind="adapter",
        source_id="a1",
        severity="critical",
        message=f"Request failed: {error}"
    )
    await bus.publish_nowait(alert)
```

### 2. 痛觉聚合

系统会话（system session）的 Worker 接收 ALERT：

```python
# 在 system session 的 worker 循环中
if obs.obs_type == ObservationType.ALERT:
    # 调用 _on_system_pain()
    await self._on_system_pain(obs)
```

#### _on_system_pain() 的职责

```python
async def _on_system_pain(self, alert: Observation):
    """
    聚合痛觉信号，检测突发，可能触发自调节
    """
    pain_key = extract_pain_key(alert)  # e.g., "adapter:a1"
    
    # 更新痛觉计数器
    self.pain_state.record_pain(pain_key, severity=alert.severity)
    
    # 检查是否达到突发阈值
    if self.pain_state.is_burst(pain_key):
        # 触发保护机制
        await self._trigger_protection(pain_key)
```

### 3. 突发检测

```python
# config/gate.yaml
drop_escalation:
  burst_threshold: 5          # 连续 5 个相同痛觉
  burst_window: 60s           # 在 60 秒内
  cooldown_duration: 300s     # 触发 300 秒冷却
  overload_threshold: 0.5     # DROP 比例达到 50%
```

### 4. 保护激活

当检测到突发时：

```python
async def _trigger_protection(self, pain_key: str):
    """
    激活 emergency_mode 或其他保护机制
    """
    # 决定激活哪种模式
    if pain_key == "adapter:*":
        # Adapter 频繁失败 → 激活 emergency_mode
        self.system_reflex.activate_emergency_mode(
            duration=300,  # 5 分钟
            reason=f"Burst detected from {pain_key}"
        )
    
    elif "drop" in pain_key:
        # DROP 比例过高 → 尝试 force_low_model
        self.system_reflex.activate_low_model_mode(
            duration=300,
            reason="Drop overload detected"
        )
```

---

## Agent 建议采纳流程

### 1. Agent 发送建议

Agent 处理过程中，如果想调节系统：

```python
# 在 Agent 中
if condition_detected:
    # 建议切换到低模型
    suggestion = Observation(
        obs_type=ObservationType.CONTROL,
        control_type="tuning_suggestion",
        payload=ControlPayload(
            override_key="force_low_model",
            override_value=True,
            reason="High latency detected",
            ttl_seconds=600  # 最多 10 分钟生效
        )
    )
    await bus.publish_nowait(suggestion)
```

### 2. 建议白名单过滤

SystemReflex 收到建议：

```python
# 在 system_reflex/controller.py 中
def handle_observation(self, obs, now):
    if obs.control_type == "tuning_suggestion":
        override_key = obs.payload.override_key
        
        # 检查白名单
        if override_key not in SUGGESTION_WHITELIST:
            # 拒绝
            log_warning(f"Suggestion {override_key} not whitelisted")
            return []
        
        # 通过白名单，继续处理
        ...
```

**当前白名单**：
```python
SUGGESTION_WHITELIST = [
    "force_low_model",      # ✅ 允许
    # "emergency_mode",     # ❌ 禁止（系统自动管理）
    # 其他覆盖项            # ❌ 禁止
]
```

### 3. TTL 约束

建议必须在 TTL 内生效：

```python
# 建议有效期限制
if "ttl_seconds" in suggestion:
    ttl = min(suggestion.ttl_seconds, 3600)  # 最多 1 小时
else:
    ttl = 300  # 默认 5 分钟

effective_until = now + ttl
```

### 4. 应用建议

```python
# 如果通过所有检查
self.provider.update_overrides(**{
    override_key: override_value
})

# 发出 CONTROL(tuning_applied) 事件
applied_event = Observation(
    obs_type=ObservationType.CONTROL,
    control_type="tuning_applied",
    payload=ControlPayload(
        override_key=override_key,
        effective_until=effective_until,
        agent_reason=suggestion.reason
    )
)
```

### 5. TTL 超期自动撤销

在每次 worker 循环中：

```python
async def _evaluate_suggestion_ttl(self):
    """
    检查是否有建议过期，自动撤销
    """
    now = time.time()
    
    for override_key, state in self.suggestion_state.items():
        if state.active_until_ts < now:
            # 撤销
            self.provider.update_overrides(**{
                override_key: None  # 或默认值
            })
            
            # 发出事件
            emit CONTROL(suggestion_reverted)
            
            # 清理状态
            del self.suggestion_state[override_key]
```

---

## 完整生命周期示例

### 场景：Adapter 故障 → 自动降级 → 恢复

```
T=0s
  Adapter a1 失败
  → 生成 ALERT(adapter:a1)
  → 被 system session 接收
  
T=1s - T=60s
  Adapter a1 继续失败
  → 5 个 ALERT 聚合
  → 达到 burst_threshold
  → 触发 _trigger_protection()
  
T=61s
  SystemReflexController 决定激活 emergency_mode
  → 调用 provider.update_overrides(emergency_mode=True)
  → 发出 CONTROL(system_mode_changed, mode=EMERGENCY)
  → 记录 suggestion_state
  
T=62s - T=360s
  Gate 采用新的 emergency 阈值（提高 50%）
  → 过滤严格，DROP 更多请求
  → 但 Adapter a1 的新请求尝试
  → 逐渐恢复
  
T=361s
  SystemReflexController 在循环中检查 TTL
  → emergency_mode 超期（300s 后）
  → 调用 provider.update_overrides(emergency_mode=False)
  → 发出 CONTROL(suggestion_reverted, reason=TTL_EXPIRED)
  
T=362s onwards
  系统恢复正常阈值
  Adapter a1 继续正常工作
```

---

## 冷却和防抖

### 防止频繁切换

```python
class SuggestionState:
    def __init__(self):
        self.active_overrides = {}      # 当前激活的 overrides
        self.active_until_ts = {}       # 每个 override 的过期时间
        self.last_applied_ts = {}       # 最后一次应用时间
        self.cooldown_duration = 60     # 冷却期 60 秒
    
    def can_apply_suggestion(self, override_key: str, now: float) -> bool:
        """
        检查是否可以应用建议
        - 如果最近应用过，需要等待冷却期
        """
        if override_key in self.last_applied_ts:
            elapsed = now - self.last_applied_ts[override_key]
            if elapsed < self.cooldown_duration:
                return False
        return True
```

### 示例：fast-switching attack

```
T=0s: Agent 建议 force_low_model=True (ttl=10m)
     → 应用，last_applied_ts=0s

T=10s: Agent 建议 force_low_model=False
      → 检查冷却期：10s < 60s
      → 拒绝（防止抖动）

T=61s: Agent 建议 force_low_model=False
      → 检查冷却期：61s >= 60s
      → 允许应用

T=11m: TTL 自动超期
      → 撤销 force_low_model
```

---

## 状态管理

### SuggestionState 数据结构

```python
@dataclass
class SuggestionState:
    """
    跟踪所有激活的建议和自调节
    """
    active_overrides: dict[str, Any]      # 当前值
    active_until_ts: dict[str, float]     # 过期时间戳
    last_applied_ts: dict[str, float]     # 最后一次应用时间
    applied_reasons: dict[str, str]       # 应用理由
    cooldown_duration: float = 60.0       # 冷却期（秒）
    
    def is_active(self, override_key: str, now: float) -> bool:
        """检查是否当前激活且未过期"""
        if override_key not in self.active_until_ts:
            return False
        return self.active_until_ts[override_key] > now
    
    def record_pain(self, pain_key: str, severity: str):
        """记录一个痛觉信号"""
        # 实现痛觉计数和时间窗口
        ...
    
    def is_burst(self, pain_key: str) -> bool:
        """检查是否检测到突发"""
        # 根据 burst_threshold 和 burst_window
        ...
```

---

## 可观测性

### 关键事件

#### Event 1: Pain Alert Generated

```json
{
  "event_type": "pain_alert_generated",
  "pain_key": "adapter:a1",
  "severity": "critical",
  "timestamp": "2026-02-11T10:30:45Z",
  "message": "Request failed: Timeout"
}
```

#### Event 2: Burst Detected

```json
{
  "event_type": "burst_detected",
  "pain_key": "adapter:a1",
  "burst_count": 5,
  "burst_window": 60,
  "timestamp": "2026-02-11T10:31:00Z"
}
```

#### Event 3: System Mode Changed

```json
{
  "event_type": "system_mode_changed",
  "mode": "EMERGENCY",
  "reason": "burst_detected:adapter:a1",
  "effective_until": "2026-02-11T10:36:00Z",
  "timestamp": "2026-02-11T10:31:01Z"
}
```

#### Event 4: Tuning Suggestion Applied

```json
{
  "event_type": "tuning_applied",
  "override_key": "force_low_model",
  "override_value": true,
  "effective_until": "2026-02-11T10:41:00Z",
  "agent_reason": "High latency detected",
  "timestamp": "2026-02-11T10:31:10Z"
}
```

#### Event 5: Suggestion Reverted

```json
{
  "event_type": "suggestion_reverted",
  "override_key": "force_low_model",
  "reason": "TTL_EXPIRED",
  "timestamp": "2026-02-11T10:41:05Z"
}
```

### 监控指标

```
系统健康指标：
├─ pain_total_count         (总痛觉信号数)
├─ pain_by_key              (按来源的痛觉分布)
├─ burst_detection_count    (突发检测次数)
├─ emergency_mode_active    (emergency 是否激活)
├─ emergency_mode_duration  (当前激活时长)
├─ active_suggestions_count (激活的 Agent 建议数)
└─ suggestion_whitelist_hit_rate (白名单命中率)
```

---

## 边界和约束

### SystemReflex 不做的事

❌ 决定是否响应（Gate 的职责）
❌ 生成响应内容（Agent 的职责）
❌ 修改 Gate 的主配置文件
❌ 直接调用 Agent
❌ 持久化状态到数据库

### SystemReflex 只做的事

✅ 聚合痛觉信号
✅ 检测突发和过载
✅ 激活保护机制（emergency_mode）
✅ 评估 Agent 建议
✅ 应用建议（通过 overrides）
✅ TTL 管理和自动撤销
✅ 发出可观测事件

### Agent 的责任

✅ 发送建议（如果需要）
✅ 等待系统应用或拒绝
✅ 不能强制修改任何配置
✅ 不能绕过 SystemReflex 的白名单

---

## 测试策略

### 单元测试

1. **痛觉生成**：验证 make_pain_alert 的输出格式
2. **痛觉提取**：验证 extract_pain_key 的准确性
3. **突发检测**：验证 is_burst 的逻辑
4. **白名单过滤**：验证建议是否被正确过滤
5. **TTL 管理**：验证超期撤销
6. **冷却防抖**：验证冷却期阻止

### 集成测试

1. **Gate + SystemReflex**：完整痛觉反馈闭环
2. **Agent 建议采纳**：建议流程端到端
3. **TTL 自动撤销**：时间推进和自动恢复
4. **多建议竞争**：多个建议同时激活时的处理

### 压力测试

- 高频率痛觉信号（验证聚合性能）
- 多个 Agent 竞争建议（验证防抖）
- 配置热更新中的 TTL 推进（验证一致性）

---

## 常见问题

### Q: 为什么 emergency_mode 由系统自动管理？

**A**: emergency_mode 代表系统的防御状态。如果 Agent 能随意控制，可能导致恶意降级或正常请求被过滤。因此只允许 Agent 建议其他参数。

### Q: TTL 可以永久生效吗？

**A**: 不可以。最长 TTL 受上限限制（通常 1 小时）。超过上限的请求会被截断。这防止了 Agent 的一次性决策对系统的永久影响。

### Q: 能否同时激活多个建议？

**A**: 可以。但每个建议都有独立的 TTL 和冷却期。系统会检查是否有冲突（如同时激活 force_low_model=True 和 force_low_model=False），并拒绝不一致的建议。

### Q: 如何禁用 SystemReflex？

**A**: 删除 system session 的痛觉处理或不启动 SystemReflexController 即可。但不建议这样做，因为系统会完全缺少自保护能力。

### Q: 痛觉信号是否可以人工注入？

**A**: 可以。任何代码都可以调用 `make_pain_alert()` 生成 ALERT。但建议通过受控的方式（如日志监控器）来做，避免误报。

