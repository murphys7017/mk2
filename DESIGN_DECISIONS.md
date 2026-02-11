# MK2 设计决策文档

**记录核心架构决策、权衡分析和未来演进路线**

---

## 1. 核心设计决策

### 决策 #1: 基于快照的无锁配置热加载

**上下文**: Gate 配置需要在运行时动态更新（Agent 建议、紧急模式），但需要保证线程安全。

**选项**:

| 选项 | 优点 | 缺点 | 选中 |
|------|------|------|------|
| **快照 + 引用替换** | 无锁, 快速, GIL 保证, 简单 | 每个更新分配新对象 | ✅ |
| **RwLock** | 多读优化, 标准模式 | 引入锁, 复杂性, 死锁风险 | ❌ |
| **Queue + Poller** | 异步安全, 事件驱动 | 延迟, 消息堆积, 复杂 | ❌ |
| **Copy-on-Write** | 原子, 显式 | 内存开销大, 复杂序列化 | ❌ |

**决策**: **快照 + 引用替换**

**实现**:

```python
class GateConfigProvider:
    def __init__(self, yaml_path):
        self._ref = GateConfig.from_yaml(yaml_path)  # 初始加载
        self._path = yaml_path
        self._mtime = os.path.getmtime(yaml_path)
    
    def snapshot(self):
        """快速路径: O(1), 无锁"""
        return self._ref  # 直接返回当前引用
    
    def reload_if_changed(self):
        """检查 mtime, 需要则加载新配置"""
        new_mtime = os.path.getmtime(self._path)
        if new_mtime != self._mtime:
            new_ref = GateConfig.from_yaml(self._path)
            self._ref = new_ref  # 原子引用替换 (GIL 保证)
            self._mtime = new_mtime
    
    def update_overrides(self, **kwargs):
        """创建新快照并替换"""
        new_ref = self._ref.with_overrides(**kwargs)
        if new_ref is self._ref:
            return False  # 无变化
        self._ref = new_ref
        return True  # 有变化
```

**权衡分析**:

- ✅ **写入延迟**: O(1) 引用替换 (微秒级)
- ✅ **读取延迟**: O(1) snapshot() (纳秒级, 无锁)
- ✅ **一致性**: 强一致性 (每个 obs 看到一致的配置)
- ⚠️ **内存**: 每次更新分配新对象 (GC 处理)
- ⚠️ **热加载频率**: mtime 精度 (秒级, 足够)

**验证**: 
- ✅ `test_gate_config_hot_reload.py`: 文件改变后 1 个 obs 内生效
- ✅ `test_gate_config_loading.py`: 覆盖应用正确性

---

### 决策 #2: 串行 Worker 对会话的消费

**上下文**: 每个会话有多个观察进来, 需要按顺序处理 (state 一致性), 同时避免阻塞其他会话。

**选项**:

| 选项 | 优点 | 缺点 | 选中 |
|------|------|------|------|
| **全局串行队列** | 简单, 强一致性 | 一个会话卡住整个系统 | ❌ |
| **每会话串行 Worker** | 会话隔离, 无争用, 可扩展 | 多个任务开销 | ✅ |
| **线程池 + 会话锁** | 资源共享 | 锁竞争, 死锁风险, 调试难 | ❌ |
| **Coroutine 队列** | 轻量, asyncio 原生 | 仍需同步会话数据 | 部分 |

**决策**: **每会话串行 Worker (asyncio Task)**

**实现**:

```python
class Core:
    async def start(self):
        self._workers = {}  # {session_key: Task}
        self._states = {}   # {session_key: SessionState}
        self.router.subscribe(self._handle_observation)
    
    async def _handle_observation(self, obs: Observation):
        """InputBus 订阅回调, 分发到会话 inbox"""
        session_key = obs.session_key
        if session_key not in self.router._inboxes:
            self.router._inboxes[session_key] = asyncio.Queue()
        await self.router._inboxes[session_key].put(obs)
        
        # 首次创建会话时, 启动 worker
        if session_key not in self._workers:
            self._workers[session_key] = asyncio.create_task(
                self._session_loop(session_key)
            )
    
    async def _session_loop(self, session_key: str):
        """单个会话的串行消费者"""
        inbox = self.router._inboxes[session_key]
        state = SessionState()
        self._states[session_key] = state
        
        try:
            while not self.should_stop():
                obs = await asyncio.wait_for(
                    inbox.get(),
                    timeout=0.1
                )
                state.record(obs)
                
                # Gate 处理
                ctx = GateContext(state=state, config=self.config_provider.snapshot())
                outcome = await self.gate.handle(obs, ctx)
                
                # 执行 outcome
                for emit_obs in outcome.emit:
                    await self.bus.publish(emit_obs)
                for ingest_obs in outcome.ingest:
                    # 路由到池
                    if outcome.decision.action == GateAction.SINK:
                        self.gate.sink_pool.append(ingest_obs)
                    else:
                        self.gate.drop_pool.append(ingest_obs)
        
        except asyncio.CancelledError:
            # 清理
            state = self._states.pop(session_key, None)
            self._workers.pop(session_key, None)
            raise
```

**权衡分析**:

- ✅ **会话隔离**: 一个会话卡住不影响其他
- ✅ **状态一致性**: 单线程/协程, 无竞争
- ✅ **可扩展性**: O(n) 会话 = O(n) 任务 (轻量)
- ⚠️ **任务开销**: 100+ 会话 = 100+ Task (可接受, 每个 ~1KB)
- ⚠️ **GC 复杂性**: 需要正确清理任务和状态

**验证**:
- ✅ `test_core_metrics_0.py::test_session_isolation`: 多会话不互影响
- ✅ `test_session_gc.py`: 会话正确清理

---

### 决策 #3: Pain-driven Adapter Cooldown (痛觉驱动适配器冷却)

**上下文**: Adapter 故障 (连接错误、解析失败等) 会导致高错误率, 需要自动降级而非立即重启。

**选项**:

| 选项 | 优点 | 缺点 | 选中 |
|------|------|------|------|
| **立即重启** | 简单 | 可能陷入重启循环, 浪费资源 | ❌ |
| **指数退避** | 自然降级, 标准模式 | 需要状态跟踪每个 adapter | ⚠️ |
| **痛觉计数 → 冷却** | 自动检测, 聚合多源, 可审计 | 延迟, 依赖 ALERT obs | ✅ |
| **外部健康检查** | 显式, 独立监控 | 延迟, 额外系统 | ❌ |

**决策**: **痛觉计数 → 冷却**

**实现**:

```python
# src/nociception.py
class Nociception:
    PAIN_WINDOW_SECONDS = 60
    PAIN_BURST_THRESHOLD = 5  # 5 个痛觉 → 冷却
    ADAPTER_COOLDOWN_SECONDS = 300  # 5 分钟

# Adapter 捕获异常
try:
    data = await adapter.read()
except Exception as e:
    pain_obs = make_pain_alert(
        source_kind="adapter",
        source_id=adapter.name,
        severity="HIGH",
        exception_type=type(e).__name__
    )
    await bus.publish(pain_obs)

# Core 聚合痛觉
async def _on_system_pain(self):
    # 统计最近 60 秒的 ALERT obs
    pain_total = self.metrics.pain_total
    
    if pain_total >= PAIN_BURST_THRESHOLD:
        # 触发冷却
        self.metrics.adapter_cooldowns[adapter_name] = now + 300
        # HardBypass 会检查这个 dict, 自动 DROP 该 adapter 的 obs
        self.metrics.fanout_suppress_until = now + 60  # 防止扇出

# Gate 检查冷却
class HardBypass(GateStage):
    async def apply(self, wip: GateWip) -> GateWip:
        if wip.obs.source_name in self.core.metrics.adapter_cooldowns:
            cooldown_until = self.core.metrics.adapter_cooldowns[...]
            if now < cooldown_until:
                return GateWip(..., action=GateAction.DROP)  # 自动 DROP
```

**权衡分析**:

- ✅ **自动化**: 无需手动干预
- ✅ **聚合**: 来自多个 adapter 的错误统一响应
- ✅ **可恢复**: 冷却有时限, 自动恢复
- ⚠️ **延迟**: 需要等待 ALERT obs 发送 (几秒)
- ⚠️ **粗粒度**: 阈值固定 (5 次), 不能细调单个 adapter

**验证**:
- ✅ `test_nociception_v0.py::test_burst_triggers_cooldown`: 5 个痛觉 → 冷却
- ✅ `test_core_metrics_0.py`: 冷却状态记录

---

### 决策 #4: Scene 场景推理 vs. 手工标签

**上下文**: 观察需要分类 (DIALOGUE, GROUP, ALERT 等) 以便应用不同的门控策略。

**选项**:

| 选项 | 优点 | 缺点 | 选中 |
|------|------|------|------|
| **Adapter 标注场景** | 准确, Adapter 最了解 | 依赖 Adapter 实现, 可能不标 | ❌ |
| **SceneInferencer (规则)** | 自动, 独立于 Adapter, 可扩展 | 可能误分类, 需要维护规则 | ✅ |
| **LLM 分类** | 高准确度 | 高延迟, 高成本, 外部依赖 | 未来 |
| **混合 (优先用标注, 后备规则)** | 两全其美 | 复杂性, 验证困难 | 可选 |

**决策**: **SceneInferencer (规则)**

**实现**:

```python
class SceneInferencer(GateStage):
    """根据观察属性推理场景"""
    
    async def apply(self, wip: GateWip) -> GateWip:
        obs = wip.obs
        
        # 显式标记
        if hasattr(obs.payload, 'scene'):
            return GateWip(..., scene=obs.payload.scene)
        
        # 根据 obs_type 推理
        if obs.obs_type == ObservationType.MESSAGE:
            text = obs.payload.text
            if self._is_group_message(text):  # @多个人
                scene = Scene.GROUP
            else:
                scene = Scene.DIALOGUE
        elif obs.obs_type == ObservationType.ALERT:
            scene = Scene.ALERT
        else:
            scene = Scene.SYSTEM
        
        return GateWip(..., scene=scene)
    
    def _is_group_message(self, text: str) -> bool:
        # 检查 @mention 多个用户
        mention_count = len(re.findall(r'@\w+', text))
        return mention_count >= 2
```

**规则**:

| 特征 | 推理 |
|------|------|
| obs_type = ALERT | Scene.ALERT |
| obs_type = MESSAGE + @多人 | Scene.GROUP |
| obs_type = MESSAGE + @无/单人 | Scene.DIALOGUE |
| obs_type = SYSTEM | Scene.SYSTEM |

**权衡分析**:

- ✅ **自动化**: 无需 Adapter 修改
- ✅ **一致性**: 统一逻辑
- ⚠️ **准确度**: 规则可能有漏洞 (e.g., 群组识别)
- ⚠️ **维护成本**: 需要更新规则应对新场景

**改进方向** (Phase 7+):
- 支持 Adapter 显式提供 scene (覆盖推理)
- 添加 LLM 推理作为高精度选项
- 学习历史准确率, 自适应规则

**验证**:
- ✅ `test_gate_mvp.py::test_scene_inference`: 各场景推理正确

---

### 决策 #5: Agent 建议白名单 vs. 自由覆盖

**上下文**: Agent 需要请求系统调整 (如 force_low_model), 但不能随意改变所有参数 (如 emergency_mode)。

**选项**:

| 选项 | 优点 | 缺点 | 选中 |
|------|------|------|------|
| **白名单 (force_low_model 仅)** | 安全, 可控, 可审计 | 灵活性低, 可能需要 hardcode | ✅ |
| **灰名单 (允许调整但有范围限制)** | 更灵活 | 复杂度高, 需要验证规则 | 未来 |
| **无限制** | 简单 | 危险, Agent 可破坏系统配置 | ❌ |
| **需要 Admin 批准** | 极端安全 | 延迟高, 破坏自主性 | ❌ |

**决策**: **白名单**

**实现**:

```python
class ReflexConfig:
    agent_override_whitelist: tuple = ("force_low_model",)

class SystemReflexController:
    def handle_tuning_suggestion(self, obs):
        suggested = obs.payload.data.get("suggested_overrides", {})
        
        # 白名单过滤
        approved = {}
        for key, value in suggested.items():
            if key in self.config.agent_override_whitelist:
                approved[key] = value
            else:
                # 拒绝 (日志记录)
                logger.warning(f"Override '{key}' not whitelisted")
        
        # 应用已批准的
        if approved:
            self.config_provider.update_overrides(**approved)
            return True
        return False
```

**白名单参数定义**:

| 参数 | 含义 | 允许值 | Agent 控制权 |
|------|------|--------|------------|
| force_low_model | 强制低优先级模型 | True/False | ✅ 允许 |
| emergency_mode | 系统紧急模式 | True/False | ❌ 系统仅 |
| drop_escalation threshold | DROP 警告阈值 | 整数 | ❌ 配置仅 |

**权衡分析**:

- ✅ **安全性**: Agent 无法破坏关键参数
- ✅ **可审计**: 白名单显式列出允许项
- ⚠️ **灵活性**: 新场景需要改代码 (不能配置)
- ⚠️ **硬编码**: 白名单需要在代码中定义

**改进方向**:
- 将白名单移到 config/gate.yaml (配置驱动)
- 为每个白名单项定义值范围验证规则
- 添加 audit log (谁在什么时间建议了什么)

**验证**:
- ✅ `test_system_reflex_v2_agent_suggestion.py::test_whitelist_blocks_emergency_mode`: emergency_mode 被拒
- ✅ 同文件::test_suggestion_applied_force_low_model: force_low_model 被接受

---

## 2. 架构权衡

### 权衡 #1: 中央编排 vs. 分布式消息

**MK2 架构选择**: **中央编排 (Core 为中心)**

```
Adapter → Bus → Router → Worker → Gate → Pool
                                    ↑
                          Core 管理所有资源
                     (状态, 指标, 配置, GC)
```

**优点**:
- 简单集中管理
- 调试容易 (一个日志来源)
- 性能可控

**缺点**:
- Core 是单点 (故障影响全系统)
- 扩展性受限 (难以分布式部署)

**替代方案** (未来):
- 发布/订阅模型 (RabbitMQ/Kafka)
- 多核心协调 (一致性哈希)

---

### 权衡 #2: 同步 Gate vs. 异步 Gate

**MK2 架构选择**: **同步 Gate (阻塞式)**

```python
outcome = await gate.handle(obs, ctx)  # 等待返回
execute(outcome)
```

**优点**:
- 简单, 易于追踪
- 执行顺序清晰
- 调试友好

**缺点**:
- 一个阶段慢会阻塞后续
- 不能并行多阶段

**优化** (可选):
- 将昂贵阶段异步化 (e.g., LLM 推理)
- 使用 batching 提高吞吐

---

### 权衡 #3: in-memory Pools vs. 持久化 Storage

**MK2 架构选择**: **in-memory Pools (简单快速)**

```python
self.sink_pool = deque(maxlen=1000)  # 环形缓冲
self.drop_pool = deque(maxlen=1000)
```

**优点**:
- 快速 (无 IO)
- 简单实现

**缺点**:
- 系统重启丢失
- 容量固定

**改进方向**:
- 定期 flush 到文件/DB
- 可配置容量
- 压缩存储 (只保留指标汇总)

---

## 3. 已弃用的设计

### 设计 ❌: Global GIL-based Metrics Lock

**为什么弃用**: Python GIL 已保证简单整数操作的原子性, 额外的 lock 会降低性能且增加死锁风险。

```python
# ❌ 不需要 (过度设计)
self.metrics_lock = asyncio.Lock()
async with self.metrics_lock:
    self.metrics.pain_total += 1

# ✅ 足够了 (GIL 保证)
self.metrics.pain_total += 1
```

---

### 设计 ❌: 每个 Adapter 独立的错误重试策略

**为什么弃用**: Adapter 错误需要全局协调 (不能某个 adapter 频繁重试导致资源耗尽)。使用全局 Nociception + 统一 Cooldown 更优。

```python
# ❌ 分散, 难以协调
class TextAdapter:
    async def retry_with_backoff(self):
        for i in range(5):
            await asyncio.sleep(2 ** i)
            try:
                return await self.read()
            except:
                pass

# ✅ 集中管理
pain_obs = make_pain_alert(...)
# Core 监控痛觉 → 冷却所有该源的 adapter
```

---

### 设计 ❌: 复杂的 Dedup 指纹 (MD5)

**为什么弃用**: MD5 计算开销大, 对于高吞吐系统 (200+ obs/sec/worker) 不必要。使用简单哈希足够。

```python
# ❌ 复杂
fingerprint = hashlib.md5(obs.payload.text.encode()).hexdigest()

# ✅ 简单快速
fingerprint = hash((obs.source_name, obs.payload.text[:100]))
```

---

## 4. 性能模型

### 延迟分解 (单个观察)

```
InputBus.publish(obs)      ~0.1ms  (队列入队)
  ↓
SessionRouter 分发          ~0.05ms (dict lookup)
  ↓
SessionWorker 消费          ~0.2ms  (asyncio 调度)
  ├─ Gate.handle()          ~2-5ms  (主要开销)
  │  ├─ SceneInferencer    ~0.1ms
  │  ├─ HardBypass         ~0.05ms
  │  ├─ FeatureExtractor   ~0.5ms
  │  ├─ ScoringStage       ~0.2ms
  │  ├─ Deduplicator       ~0.5ms  (dict + deque lookup)
  │  ├─ PolicyMapper       ~0.1ms
  │  └─ FinalizeStage      ~0.05ms
  ├─ Execute outcome        ~0.5ms  (emit/ingest + 指标更新)
  └─ 回到 inbox.get()       ~0.1ms

总计: ~2.8-6ms per obs
```

### 吞吐量分解

```
单 Worker 容量:
  - Gate 处理: 200-400 obs/sec (5ms 延迟)
  - 有 10 个 Worker (10 会话): 2000-4000 obs/sec
  - 有 100 Worker (100 会话): 20000-40000 obs/sec

限制因素:
  - Gate 管道宽度 (单核)
  - 适配器生成速率
  - 总线缓冲大小 (bus_maxsize=1000)
```

### 内存使用

```
基础:
  - Core 对象: ~1MB
  - 配置 (YAML): ~50KB
  - 指标: ~100KB

per-session:
  - SessionState: ~5KB (recent_obs deque)
  - Worker Task: ~1KB

per-observation (缓存中):
  - Observation 对象: ~500B
  - Dedup 指纹: ~100B

规模估算 (1000 会话, 缓冲 1000 obs):
  基础 (1.15MB) 
  + 1000 会话 × 5KB = 5MB
  + 1000 obs × 0.6KB = 0.6MB
  ≈ 6.75MB (小于 100MB, 安全)
```

---

## 5. 安全考虑

### 威胁模型

| 威胁 | 影响 | 缓解 |
|------|------|------|
| 恶意 Adapter 产生无限 obs | DoS | 队列限制 (bus_maxsize) + GC 清理 |
| Agent 破坏配置 | 系统崩溃 | 白名单 + TTL + 审计日志 |
| 高频痛觉伪造 (冷却滥用) | 服务中断 | ALERT obs 计数阈值 + 手工审查 |
| 配置文件被篡改 | 策略绕过 | 文件权限 (mode 640) + 备份 |
| 内存泄漏 (OOM) | 崩溃 | 监控内存, 定期重启, 会话超时 |

### 审计与可观测性

**生成的审计事件**:
- 每个 Agent 建议 → CONTROL(tuning_suggestion)
- 每个建议应用 → CONTROL(system_mode_changed)
- 每个 TTL 过期 → CONTROL(tuning_reverted)
- 每个痛觉突发 → 指标记录

**日志建议**:

```bash
# 审计日志 (分离存储)
grep "tuning_suggestion\|system_mode_changed" logs/mk2.log > logs/audit.log

# 告警规则
- pain_total > 50 in 60s → 通知管理员
- adapter_cooldown > 5 → 通知管理员
- bus queue 深度 > 90% → 通知管理员
```

---

## 6. 未来演进路线

### Phase 7: 验证与工具集成
- [ ] Validator 阶段: 验证建议 payload 结构
- [ ] Tool result obs 路由到 ToolPool
- [ ] Agent 可访问工具历史

### Phase 8: Intent 与技能
- [ ] 规则基础的 intent 分类
- [ ] 可扩展的技能框架

### Phase 9: 可观测性
- [ ] Prometheus 指标导出
- [ ] Jaeger 分布式追踪
- [ ] 集中化日志聚合

### Phase 10: 分布式与高可用
- [ ] 多核心协调
- [ ] 消息队列 (Kafka/RabbitMQ) 集成
- [ ] 会话持久化

### Phase 11: 高级功能
- [ ] LLM 驱动的场景推理
- [ ] 动态规则学习
- [ ] 多模态观察支持

---

## 7. 参考与引用

### 相关论文
- "The Google File System" (GFS) - 流式处理设计启发
- "Raft: In Search of an Understandable Consensus Algorithm" - 分布式协调

### 开源参考
- asyncio 官方文档 (协程设计)
- dataclasses PEP 557 (序列化友好的数据模型)
- YAML 1.2 规范

---

**文档版本**: 1.0  
**最后更新**: Session 10  
**维护者**: Architecture Team
