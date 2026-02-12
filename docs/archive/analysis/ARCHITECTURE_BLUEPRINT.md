# mk2 架构梳理 - Evidence Pipeline 扩展指南

**文档目的**：为引入新的 Agent / Evidence Pipeline 提供"可指导重构"的架构分析，而非简单文件列表。

---

## 1️⃣ 项目目标 - 从代码推断

### 核心问题定义

**系统正在解决的问题**：
- **多源异步输入的实时处理**：来自多个 adapter（文本、timer、alert）的事件需要在**同一个 Core** 中被**串行化、路由、过滤**后进入不同的处理分支
- **Session 隔离 + 共享系统状态**：每个对话/用户是一个独立 session，但需要响应全局系统事件（System session）
- **智能网关决策**：Gate 不是简单的过滤器，而是一个**评分系统**，根据观察的类型/内容/频率决定 DELIVER/SINK/DROP
- **Agent-on-Demand**：LLM 调用不是脉冲式（单次请求-响应），而是嵌入在**长期运行的会话工作流**中

### Core 运行模型

```
事件驱动 + 多 Session 隔离 + 消息总线模式
```

**关键特征**：

| 特性 | 实现 |
|------|------|
| **输入源** | 多个 Adapter（push → publish_nowait）|
| **消息总线** | AsyncInputBus（无阻塞队列，满则丢）|
| **路由层** | SessionRouter（一对一映射到 per-session inbox）|
| **Worker 模型** | 每个 session 一个长期协程（_session_loop）|
| **决策层** | DefaultGate（评分 + 规则引擎 → GateOutcome）|
| **Agent 入口** | DELIVER 分支后调用 DefaultAgentOrchestrator |
| **反馈回路** | Agent 可 emit 新观察 → 重新进总线 |
| **系统级行为** | System session 处理全局事件（pain/tick/fanout）|

**数据流方向**：
```
Adapter(push_nowait) 
    ↓
AsyncInputBus (drop_when_full)
    ↓
SessionRouter.run() (async iter bus → route to inbox)
    ↓
Per-Session Inbox (FIFO deque)
    ↓
_session_loop() worker (async consume + process each obs)
    ↓
Gate.handle() (eval + decision)
    ↓
[Branch: DROP | SINK | DELIVER]
    ↓
DELIVER → Agent.handle() → emit back to bus
```

---

## 2️⃣ 运行时主流程 - 时序分解

### 完整的观察处理路径

```
User Input (TextInputAdapter.ingest_text)
    ↓ [1] publish_nowait (同步，不阻塞 adapter)
AsyncInputBus
    ↓ [2] async for obs in bus (Router.run 中)
SessionRouter.run()
    ↓ [3] route by session_key → inbox.put_nowait()
SessionInbox (per-session FIFO)
    ↓ [4] await inbox.get() (_session_loop 中)
Worker._session_loop(session_key)
    ├─ [5a] state.record(obs)  [更新 SessionState]
    ├─ [5b] Gate.handle(obs, ctx)  [评分决策]
    │    ├─ pipeline.run()  [规则评估]
    │    ├─ score calculation
    │    └─ action decision
    │
    ├─ [6] Emit handling
    │    └─ for emit_obs in outcome.emit: bus.publish_nowait()  [反馈]
    │
    ├─ [7] Action branch
    │    ├─ DROP: skip
    │    ├─ SINK: skip (或到 sink_pool)
    │    └─ DELIVER:
    │         │
    │         ├─ [8a] agent_req = AgentRequest(obs, decision, state, now)
    │         │
    │         ├─ [8b] agent_resp = Agent.handle(agent_req)
    │         │            ├─ Planner.build_plan(req)
    │         │            │   └─ RulePlanner 根据关键词决定 plan
    │         │            ├─ 执行 step
    │         │            │   ├─ SKILL: e.g., get_time
    │         │            │   └─ AGENT: e.g., dialogue_agent.reply()
    │         │            │         └─ LLM.call(messages)
    │         │            └─ 构造 AgentResponse(emit=[obs], success=bool)
    │         │
    │         └─ [8c] for emit_obs in agent_resp.emit: bus.publish_nowait()
    │
    └─ [9] Loop next obs
```

### 关键控制点分析

#### 同步控制点（阻塞传播）

| 位置 | 机制 | 影响范围 |
|------|------|--------|
| **Adapter.ingest_text()** | TextInputAdapter 投递 → publish_nowait 同步返回 | Adapter 线程不阻塞（设计目标）|
| **Bus.publish_nowait()** | Try-except put_nowait，满则丢 | 无等待，Adapter 立即返回 |
| **Router.__next__()** | 轮询 0.5s timeout | Router 可控地让出 CPU |
| **Gate.handle()** | 同步评分/规则/决策 <10ms | blocking worker |
| **LLM.call(messages)** | **同步调用 HTTP API** | ⚠️ **长阻塞** (秒级) |

#### 长期运行的协程

| 协程 | 启动位置 | 生命周期 | 职责 |
|------|--------|--------|------|
| **router.run()** | Core._startup | 直到 bus.close() | 从 bus 迭代 → 路由到 inbox |
| **_watch_new_sessions()** | Core._startup | 直到 _closing | 轮询 list_active_sessions → 启动新 worker |
| **_session_loop(session_key)** | _watch_new_sessions → _ensure_worker | 直到 cancel/exception | 消费 inbox → 执行 obs 链路 |
| **_session_gc_loop()** | Core._startup (可选) | 直到 cancel | 定期扫描 idle session → gc |

#### Shutdown / Cancel 机制传播

```
main: asyncio.run(core.run_forever())
  ├─ Core._startup()
  │   ├─ router_task = asyncio.create_task(router.run())
  │   ├─ watcher_task = asyncio.create_task(_watch_new_sessions())
  │   ├─ gc_task = asyncio.create_task(_session_gc_loop())  [optional]
  │   └─ for cada session: worker_task = asyncio.create_task(_session_loop(key))
  │
  └─ await router_task  [等待 router，通常无限期]
       ↑ [KeyboardInterrupt / Ctrl+C]
       └─ CancelledError
           │
           └─ finally: Core._shutdown()
               ├─ adapter.stop()  [同步]
               ├─ bus.close()  [标记 _closed = True]
               ├─ [取消所有 tasks]
               │   ├─ router_task.cancel()
               │   ├─ watcher_task.cancel()
               │   ├─ worker_tasks.cancel()  [多个]
               │   └─ gc_task.cancel()
               │
               └─ await asyncio.gather(*tasks, return_exceptions=True)
                   [最多等待 1.5s（_stop_core timeout）]
```

**关键点**：
- Shutdown 是**级联的**：bus.close() → router 自然退出 → watcher 检测无新 session → worker 逐个结束
- Worker 内 LLM.call() 是同步的，**无法被 CancelledError 中断**（除非 Python 线程中断)
- 因此 shutdown 时可能**卡在 LLM 调用**，需要给 LLM 添加 timeout

---

## 3️⃣ 目录结构与职责映射

### src/core.py - 主编排器

**职责**：
- 生命周期管理（启动、运行、关闭）
- Task 编排（router、watcher、gc、workers）
- Session 隔离与状态管理
- Observation 流水线入口（处理 system vs user）
- Pain 聚合与 Nociception 保护机制

**依赖**：
- AsyncInputBus（消息总线）
- SessionRouter（路由）
- DefaultGate（决策）
- DefaultAgentOrchestrator（处理）
- SystemReflexController（系统级反射）

**独立性**：❌ 不可完全独立替换（太多组件耦合），但**架构清晰**分层

---

### src/input_bus.py - 异步消息总线

**职责**：
- 双模态接口：Adapter 端 sync publish_nowait，Core 端 async iter
- 无阻塞丢弃政策（drop_when_full）
- 基础 metrics（published, dropped, consumed）

**设计洞察**：
```python
# Adapter 端：同步，不能阻塞
result = bus.publish_nowait(obs)  # 立即返回 PublishResult

# Core 端：异步迭代
async for obs in bus:
    await _process(obs)
```

**依赖**：无依赖（最底层）

**独立性**：✅ 完全可独立替换（例：改成 Redis streams、gRPC 等）

---

### src/session_router.py - 会话路由

**职责**：
- Observation 会话密钥确定（如需要）
- 一对一映射到 per-session inbox（FIFO）
- Active session 追踪
- Session isolation 保证

**数据结构**：
```
Bus → Router.run() (async iter)
  └─ for obs: route to self._inboxes[session_key]
     └─ SessionInbox(maxsize=256, FIFO)
        └─ Worker await inbox.get()
```

**依赖**：AsyncInputBus

**独立性**：✅ 可独立替换（例：改成 hash ring、topic-based 等）

---

### src/gate/ - 智能网关

**结构**：
```
├─ types.py
│   ├─ GateAction: DROP, SINK, DELIVER
│   ├─ Scene: DIALOGUE, GROUP, SYSTEM, TOOL_CALL, TOOL_RESULT, ALERT
│   ├─ GateDecision: (action, scene, session_key, score, reasons, ...)
│   └─ GateOutcome: (decision, emit, ingest)
│
├─ config.py
│   └─ GateConfig (YAML loader)
│       ├─ rules: DialogueRulesConfig, GroupRulesConfig, SystemRulesConfig
│       ├─ scene_policies: Dict[Scene → ScenePolicy]
│       ├─ overrides: emergency_mode, deliver_sessions, force_low_model
│       └─ drop_escalation: burst detection, cooldown
│
├─ metrics.py
│   └─ GateMetrics (计数器)
│
├─ gate.py
│   └─ DefaultGate
│       ├─ pipeline: DefaultGatePipeline (rules apply)
│       ├─ sink_pool, drop_pool, tool_pool
│       └─ handle(obs, ctx) → GateOutcome
│
├─ pipeline/
│   └─ base.py
│       └─ DefaultGatePipeline.run(obs, ctx, wip)
│
└─ pool/
    ├─ sink_pool.py (保存 SINK 观察)
    ├─ drop_pool.py (保存 DROP 观察)
    └─ tool_pool.py (保存 TOOL_RESULT 观察)
```

**职责**：
- 观察评分（基于内容、频率、优先级）
- 规则应用（对话规则、群组规则、系统规则）
- 决策输出（DELIVER / SINK / DROP）
- 可选发射（emit 用于派生观察）
- 可选摄取（ingest 用于池存储）

**关键洞察**：
```
scoring(obs) → 0.0 ~ 1.0
  ├─ deliver_threshold = 0.7 → action = DELIVER
  ├─ sink_threshold = 0.3 → action = SINK
  └─ < 0.3 → action = DROP

rules 权重：
  dialogue: mention=0.4, question=0.15, urgent=0.3
  group: mention=0.6, whitelist=0.25
  system: base=0.0 (usually ALERT → DELIVER)
```

**依赖**：
- GateConfig（配置）
- SessionState（上下文）

**独立性**：⚠️ 半独立（内部规则紧耦合，但可换成 ML 模型）

---

### src/session_state.py - 会话状态

**职责**：
- 轻量级状态容器（非持久化）
- 活跃时间追踪
- 最近观察缓存（deque, maxlen=20）
- GC 候选评判

**不是**：
- 对话历史（那应该在 Memory/Context）
- 持久存储
- 完整用户模型

**依赖**：无

**独立性**：✅ 完全独立

---

### src/agent/ - Agent 编排系统

#### src/agent/orchestrator.py - 主编排器

**职责**：
- LLM gateway 初始化（从 config）
- Planner、Dialogue、Skills 协调
- AgentRequest → AgentResponse 转换

**关键流程**：
```
AgentRequest(obs, decision, state, now)
  ├─ Planner.build_plan(req)
  │  └─ RulePlanner (keyword match)
  │     ├─ if "时间" in text → SKILL:get_time
  │     └─ else → AGENT:dialogue
  │
  ├─ for step in plan:
  │    ├─ if SKILL → skill.run()
  │    └─ if AGENT → dialogue_agent.reply(req)
  │         └─ LLM.call(messages)
  │
  └─ AgentResponse(emit=[obs], success=True)
```

**依赖**：
- LLMGateway（模型调用）
- RulePlanner（决策）
- SimpleDialogueAgent（对话）
- Skills（基础技能）

**独立性**：⚠️ 半独立（Planner 规则硬编码，但可扩展）

#### src/agent/types.py - 类型定义

```
AgentRequest: obs, decision, state, now
Step: type (SKILL/AGENT/TOOL), target, params
Plan: steps[], reason
AgentResponse: emit[], success, error
```

#### src/agent/planner.py - 规则计划器

**当前实现**：
```python
if "时间" in text:
    return Plan(steps=[Step(SKILL, "get_time")])
else:
    return Plan(steps=[Step(AGENT, "dialogue")])
```

**限制**：完全基于关键词，无 intent/semantic

#### src/agent/dialogue_agent.py - 对话代理

**职责**：
- 消息构建
- LLM.call()

**依赖**：LLMClient

#### src/agent/skills/ - 技能库

**当前**：仅 GetTimeSkill

**扩展点**：添加新 skill → register in orchestrator

---

### src/llm/ - 统一 LLM 接口

**结构**：
```
├─ base.py
│   ├─ LLMClient (Protocol)
│   ├─ ProviderSettings
│   └─ ModelSettings
│
├─ config.py
│   └─ LLMConfig (YAML loader)
│       ├─ load(path) → parse yaml
│       ├─ resolve_env_placeholder()
│       └─ default_provider / default_models
│
├─ client.py
│   └─ LLMGateway
│       ├─ from_config(provider, model)
│       └─ call(messages, model, params)
│
├─ registry.py
│   └─ create_provider(name, settings)
│
└─ providers/
    ├─ ollama.py
    │   └─ OllamaClient
    │       └─ HTTP POST /api/chat
    │
    └─ bailian_openai.py
        └─ BailianOpenAIClient
            └─ HTTP POST /v1/chat/completions (OpenAI-compat)
```

**职责**：
- Provider abstraction（ollama, bailian, future: openai, claude）
- Configuration with env var support
- Model parameter normalization
- Unified call signature

**依赖**：仅 urllib（无重型依赖）

**独立性**：✅ 高度模块化，可继续添加 provider

---

### src/schemas/observation.py - 观察定义

**职责**：
- 跨系统统一数据格式
- ObservationType 枚举
- Payload 多态（MessagePayload, AlertPayload, SchedulePayload）

**关键**：
```
Observation:
  obs_id, obs_type, source_name/kind, session_key, actor, timestamp, payload
```

**独立性**：✅ 纯数据模型

---

### src/ 其他模块

#### system_reflex.py
- System session 的反射行为
- CONTROL 类型观察处理

#### nociception/
- Pain aggregation
- Burst detection
- Cooldown 管理
- Fanout suppression

#### config_provider.py
- Gate 配置热加载

---

## 4️⃣ 当前已存在的 Agent 能力雏形

| 能力 | 状态 | 实现 | 备注 |
|------|------|------|------|
| **Planning** | ✅ **存在** | RulePlanner (关键词规则) | 仅支持时间/对话分支，无语义理解 |
| **Tool 调用** | ⚠️ **框架就位** | AgentRequest.decision 含场景标签，但未通过 tool 调用 | Step.type 支持 TOOL，但无具体实现 |
| **Memory** | ⚠️ **部分支持** | SessionState.recent_obs (deque, maxlen=20) | 轻量级，仅最近 20 条，无持久化 |
| **Context** | ✅ **完整** | AgentRequest(obs, decision, state, now) | 包含完整上下文传递 |
| **LLM Gateway** | ✅ **完成** | LLMGateway + provider registry (ollama, bailian) | 支持环境变量、默认模型选择 |
| **Reflex（系统级）** | ✅ **存在** | SystemReflexController + pain metrics | pain aggregation, cooldown, fanout suppression |
| **Skills** | ⚠️ **框架就位** | GetTimeSkill | 仅 1 个 skill，但可扩展 |
| **Dialogue** | ✅ **存在** | SimpleDialogueAgent.reply() → LLM.call() | 同步调用，无上下文累积 |

### 标记解释

- ✅ **完全就位**：可直接使用或小幅扩展
- ⚠️ **框架就位**：基础结构存在，需要功能扩展
- ❌ **缺失**：需要新增

---

## 5️⃣ 扩展点识别 - Evidence Pipeline 的切入点

### 现状：Inline Reasoning 路径

```
Obs → Gate(score) → [DELIVER] → Planner → (Dialogue | Skill) → LLM.call() → Response
                      一次性评分        硬规则             直接 LLM
                      无上下文          无信息搜索         无论证
```

### 目标：Retrieval-Augmented Reasoning 路径

```
Obs → Gate(score) → [DELIVER] → Evidence Pipeline → Planner → Agent → Response
                                 [新增]
                                 ├─ Info Extraction
                                 ├─ Knowledge Retrieval
                                 ├─ Evidence Aggregation
                                 └─ Answer Generation
```

### 最佳扩展点

#### A. 扩展点位置 1: Gate 之后、Planner 之前

**位置**：core.py > _session_loop > 第 [8a] 步

```python
# --- 当前 ---
if outcome.decision.action == GateAction.DELIVER:
    agent_req = AgentRequest(obs, decision, state, now)
    agent_resp = self.agent.handle(agent_req)

# --- 扩展后 ---
if outcome.decision.action == GateAction.DELIVER:
    # NEW: Evidence Pipeline
    evidence = await evidence_pipeline.extract_and_retrieve(obs, state, now)
    
    agent_req = AgentRequest(obs, decision, state, now, evidence=evidence)
    agent_resp = self.agent.handle(agent_req)
```

**优点**：
✅ 不改动 Gate（Gate 已稳定）
✅ 不改动 Agent 主逻辑（只添加数据）
✅ Evidence 可异步获取（利用 worker 协程）
✅ 灵活：可选择哪些 session/obs 使用 evidence

**缺点**：
❌ 单线性：Evidence 串行执行
❌ 需要修改 AgentRequest 类型
❌ 同一 worker 中 LLM 可能长阻塞

**实现复杂度**：⭐⭐ 中等

---

#### B. 扩展点位置 2: 独立的 Evidence Session

**设计**：
```
User Obs
  ├─ [路由] → user session worker (Deliver)
  └─ [分叉] → 自动生成 InfoPlan → 投递到 evidence session worker
                 ├─ Extract entities
                 ├─ Retrieve from KB
                 ├─ Aggregate evidence
                 └─ Emit evidence_obs back to user session
```

**实现**：
```python
# 在 core._handle_user_observation 中
if outcome.decision.action == GateAction.DELIVER:
    # 1. 正常处理 user obs
    agent_resp = self.agent.handle(...)
    
    # 2. 同时生成 evidence request → 投递到 evidence session
    evidence_req = EvidenceRequest(
        session_key="evidence:" + obs.session_key,
        original_obs=obs,
        info_plan=await planner.extract_info_needs(obs)
    )
    evidence_obs = make_evidence_observation(evidence_req)
    self.bus.publish_nowait(evidence_obs)
```

**优点**：
✅ 完全异步（evidence 不阻塞 user agent）
✅ Evidence 和 User 并发处理
✅ 自然分离职责
✅ 可配置是否启用 evidence

**缺点**：
❌ 需要新 session 类型（增加 active_sessions）
❌ 需要在 Planner 中识别 EVIDENCE session
❌ Evidence 结果返回需要额外逻辑

**实现复杂度**：⭐⭐⭐ 较复杂

---

#### C. 扩展点位置 3: 在 Planner 中添加 Evidence Plan Step

**设计**：
```
Plan(steps=[
    Step(EVIDENCE, "retrieve", params={"query": extract_entities(obs)}),
    Step(SKILL/AGENT, "dialogue", params={"evidence": step[0].result})
])
```

**实现**：
```python
# planner.py
def build_plan(self, req: AgentRequest) -> Plan:
    text = extract_text(req.obs)
    steps = []
    
    # 判断是否需要 evidence
    if self.should_use_evidence(text):
        steps.append(Step(EVIDENCE, "retrieve", 
                         params={"query": extract_query(text)}))
    
    steps.append(Step(AGENT, "dialogue"))
    
    return Plan(steps=steps, reason="with_evidence")

# orchestrator.py
def handle(self, req: AgentRequest):
    plan = self.planner.build_plan(req)
    context = {}
    
    for step in plan.steps:
        if step.type == "EVIDENCE":
            evidence = evidence_service.retrieve(step.params["query"])
            context["evidence"] = evidence
        elif step.type == "AGENT":
            # Pass context to agent
            text = self.dialogue_agent.reply(req, context=context)
    
    return AgentResponse(emit=[...], success=True)
```

**优点**：
✅ Planner 控制流，清晰
✅ Plan 中可混合多种 step
✅ 易于测试（Plan 显式）

**缺点**：
❌ 需要修改 Planner / Orchestrator
❌ Evidence 同步执行（可能卡住 worker）
❌ 返回给 Planner/Orchestrator 的职责重

**实现复杂度**：⭐⭐⭐ 较复杂

---

### 推荐方案：A + 配置驱动

**理由**：
1. 最小侵入式（仅在 _session_loop 中插入一行新代码）
2. Evidence 异步可选（通过配置启用）
3. 不改动 Gate / Agent / Planner 的核心逻辑
4. 可以先实现单个 evidence provider，再扩展

**小改进**：
- 将 evidence extraction 放在**异步 task** 中，避免阻塞 worker
- Evidence 结果可缓存在 state.recent_context
- Agent 在判断是否使用 evidence 时查阅 state

---

## 6️⃣ 当前架构的优点 / 限制

### 优点

| 优点 | 为什么 |
|------|--------|
| **清晰的分层** | Adapter → Bus → Router → Worker → Gate → Agent 各司其职 |
| **异步友好** | 大量使用 asyncio，多个 worker 并发 |
| **高吞吐低延迟** | publish_nowait（无等待）+ drop_when_full（防堆积）|
| **Session 隔离** | 每个 session 独立 worker，互不影响 |
| **可观测性** | State.recent_obs, metrics, gate scores, debug logs |
| **灵活的 Gate** | 规则 + 权重系统，可配置不同场景的阈值 |
| **Agent 上下文完整** | AgentRequest 包含 obs/decision/state/now，信息充足 |
| **LLM 抽象好** | Provider pattern，易于切换/扩展模型 |
| **配置外部化** | gate.yaml, llm.yaml，无需重新编译 |

---

### 限制

#### 1. **Inline Reasoning**（当前状态）

```
Agent 没有搜索 / 论证 / 回溯的能力。
一条 obs 进来 → Planner 决定 → LLM.call() 一次 → 完成。
```

**为什么卡住**：
```python
# 当前 Agent 流程
def handle(self, req: AgentRequest):
    plan = self.planner.build_plan(req)  # 基于关键词
    
    for step in plan.steps:
        if step.type == "AGENT":
            text = self.llm.call([{"role": "user", "content": req.obs.text}])
            # ❌ 无上下文，无背景知识，一次生成完整回复
    
    return AgentResponse(emit=[text])
```

**症状**：
- 回复缺少背景知识
- 无法引用事实
- 无改正/重试逻辑

#### 2. **LLM 同步调用，Worker 长阻塞**

```python
# src/agent/dialogue_agent.py
def reply(self, req): 
    messages = ...
    return self.llm.call(messages)  # ❌ sync, 可能 5-10s

# 期间该 session 的其他 obs 无法处理（也不能，因为 global GIL）
```

**改进方向**：
```python
# ✅ 理想：异步 LLM 调用
async def reply(self, req):
    return await self.llm.acall(messages, timeout=10.0)
```

#### 3. **SessionState 太轻量**

```
recent_obs: deque(maxlen=20) 只保留最近 obs，
无对话历史、用户偏好、长期 memory。
```

**不适合**：
- 多轮对话（无连贯性）
- 个性化（无用户模型）
- 持久化（数据丢失）

#### 4. **Planner 规则硬编码**

```python
# src/agent/planner.py
if "时间" in text:
    return ...
```

**限制**：
- 仅 2 个分支（时间 vs 对话）
- 无语义理解（substring match）
- 无意图识别（intent classification）
- 无法处理歧义

#### 5. **Gate 的决策上游无反馈**

```
Gate 给出 score（例 0.65），但：
- 不知道为什么 score = 0.65
- Agent 无法利用诊断信息优化回复
- 没有 confidence → fallback 链
```

**可改进**：
```python
# GateDecision 中添加
decision.diagnostics = {
    "rules_fired": ["mention", "question_mark"],
    "score_breakdown": {"mention": 0.4, "question": 0.25},
    "confidence": 0.7
}

# Agent 可利用
if decision.confidence < 0.5:
    use_conservative_response()
```

#### 6. **反馈回路不完整**

```
Agent emit → Bus → 可能再次进 Gate，
但 Gate 会再次评分，可能 DROP（负反馈循环）。
```

**理想**：
```
Agent 的回复应该设置 scene=TOOL_RESULT 或 auto-DELIVER，
而非重新评分。
```

#### 7. **Promise of "System Reflex" 未充分利用**

```
Pain aggregation + Cooldown 存在，
但 Agent 无法感知"系统当前在保护模式"，
继续生成可能很长的回复（浪费资源）。
```

---

## 7️⃣ Evidence Pipeline 的最小侵入式扩展方案

### 总体设计

```
┌─────────────────────────────────────────────────────────────┐
│ Core v0 + Evidence Pipeline (Minimal Extension)             │
└─────────────────────────────────────────────────────────────┘

User Obs
  ├─ Adapter → Bus → Router → SessionInbox
  │
  └─ _session_loop
      ├─ [新增: InfoPlan] ← determine evidence needs
      ├─ [新增: EvidenceService.retrieve()] ← async search
      ├─ Gate.handle()
      ├─ [DELIVER] → Agent with evidence context
      │         └─ Planner (maybe now semantic)
      │         └─ Dialogue / Tools
      │         └─ LLM.call(messages + evidence_context)
      │
      └─ Response Obs → Bus
```

### 新增模块

#### 1. InfoPlanner（信息需求识别）

**位置**：`src/agent/info_planner.py`

```python
class InfoPlanner:
    """
    根据 obs 抽取信息需求（InfoPlan）
    """
    
    def extract(self, obs: Observation, state: SessionState) -> InfoPlan:
        """
        返回：InfoPlan(
            queries: ["Who is X?", "What is Y?"],
            entity_types: ["PERSON", "PLACE"],
            priority: "high"
        )
        """
        text = extract_text(obs)
        
        # 简单启发式，后续可改成 NER + intent model
        if "who" in text.lower() or "多少人" in text:
            return InfoPlan(
                queries=[text],
                entity_types=["PERSON", "ORG"],
                priority="high"
            )
        elif len(text) > 100:  # 长问题可能需要背景知识
            return InfoPlan(
                queries=[text],
                entity_types=["*"],
                priority="medium"
            )
        else:
            return InfoPlan(queries=[], priority="none")

@dataclass
class InfoPlan:
    queries: List[str]
    entity_types: List[str]  # * for any
    priority: Literal["high", "medium", "low", "none"]
```

#### 2. EvidenceService（证据检索）

**位置**：`src/agent/evidence_service.py`

```python
class EvidenceService:
    """
    统一的证据检索接口
    支持多个后端（KB, RAG, Search, 等）
    """
    
    def __init__(self, providers: List[EvidenceProvider]):
        self.providers = providers
    
    async def retrieve(self, plan: InfoPlan) -> Evidence:
        """
        并发调用多个 provider，聚合结果
        """
        tasks = [
            provider.search(plan)
            for provider in self.providers
            if provider.applicable_to(plan)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 聚合、排序、截断
        return Evidence(
            snippets=aggregate(results),
            metadata={...}
        )

@dataclass
class Evidence:
    snippets: List[str]  # 相关片段
    sources: List[str]   # 来源
    confidence: float    # 0.0 ~ 1.0
    metadata: Dict[str, Any]

# Provider Protocol
class EvidenceProvider(Protocol):
    async def search(self, plan: InfoPlan) -> List[str]: ...
    def applicable_to(self, plan: InfoPlan) -> bool: ...

# 简单实现：Mock KB
class MockKBProvider:
    async def search(self, plan: InfoPlan) -> List[str]:
        # 模拟检索
        await asyncio.sleep(0.1)
        return ["Mock evidence 1", "Mock evidence 2"]
```

#### 3. 修改 AgentRequest

**位置**：`src/agent/types.py`

```python
@dataclass
class AgentRequest:
    obs: Observation
    decision: GateDecision
    state: SessionState
    now: datetime
    evidence: Optional[Evidence] = None  # [新增]
```

#### 4. Evidence Context 注入

**位置**：`src/agent/orchestrator.py`

```python
class DefaultAgentOrchestrator:
    def handle(self, req: AgentRequest) -> AgentResponse:
        # 构建 dialogue context
        context = self._build_dialogue_context(req)
        
        if req.evidence and req.evidence.snippets:
            # 注入证据
            context["evidence_snippets"] = req.evidence.snippets
            context["evidence_confidence"] = req.evidence.confidence
        
        text = self.dialogue_agent.reply(req, context=context)
        return AgentResponse(emit=[...], success=True)

# In DialogueAgent
class SimpleDialogueAgent:
    def _build_messages(self, req: AgentRequest, context: Dict) -> List[Dict]:
        messages = []
        
        # System prompt
        system_content = "你是一个有帮助的助手。"
        if "evidence_snippets" in context:
            system_content += "\n\n已获得的背景信息：\n"
            for snippet in context["evidence_snippets"]:
                system_content += f"- {snippet}\n"
        
        messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": req.obs.text})
        
        return messages
```

#### 5. 在 Core 中集成

**位置**：`src/core.py` > `_session_loop` > DELIVER 分支

```python
# 在 Core.__init__ 中
self.info_planner = InfoPlanner()
self.evidence_service = EvidenceService(
    providers=[
        MockKBProvider(),  # 或真实 KB
        # RAGProvider(...),
    ]
)

# 在 _session_loop 中，DELIVER 分支
if outcome.decision.action == GateAction.DELIVER:
    # NEW: 异步获取 evidence
    info_plan = self.info_planner.extract(obs, state)
    evidence = None
    
    if info_plan.priority != "none":
        try:
            evidence = await asyncio.wait_for(
                self.evidence_service.retrieve(info_plan),
                timeout=2.0  # Evidence 不能阻塞太久
            )
        except asyncio.TimeoutError:
            logger.warning(f"Evidence retrieval timeout for {obs.session_key}")
    
    agent_req = AgentRequest(
        obs=obs,
        decision=outcome.decision,
        state=state,
        now=datetime.now(timezone.utc),
        evidence=evidence  # 新参数
    )
    
    agent_resp = self.agent.handle(agent_req)
    
    for emit_obs in agent_resp.emit:
        self.bus.publish_nowait(emit_obs)
```

---

### 配置与可选性

**在 config_core.yaml 中添加**：

```yaml
agent:
  enable_evidence: true
  evidence_timeout: 2.0  # seconds
  
info_planner:
  strategy: "heuristic"  # or "intent_model"
  thresholds:
    long_text_len: 100
    
evidence_providers:
  - type: "mock_kb"
    enabled: true
  - type: "rag"
    enabled: false
    host: "localhost:8000"
```

**在 Core 中控制**：

```python
if config.agent.enable_evidence:
    # 启用 evidence pipeline
    self.evidence_service = EvidenceService(...)
else:
    self.evidence_service = None
```

---

### 分阶段实现

**Phase 1: 基础框架（w1-w2）**
- [ ] InfoPlanner (heuristic 版)
- [ ] MockKBProvider
- [ ] EvidenceService (single-threaded)
- [ ] AgentRequest.evidence 注入
- [ ] Core 集成（带 timeout）

**Phase 2: 质量改进（w3-w4）**
- [ ] Semantic intent detection (BERT / 小模型)
- [ ] 真实 KB / RAG Backend 接入
- [ ] Evidence 排序 / 去重
- [ ] RetrievalAugmentedAgent (多轮检索)

**Phase 3: 生产化（w5+）**
- [ ] Evidence cache（Redis）
- [ ] Async LLM.call()
- [ ] Advanced fallback 链
- [ ] A/B testing framework

---

### 测试策略

```python
# tests/test_evidence_pipeline.py

@pytest.mark.asyncio
async def test_evidence_extraction():
    """测试 InfoPlan 抽取"""
    planner = InfoPlanner()
    obs = make_obs("Who is Alice?")
    plan = planner.extract(obs, SessionState("test"))
    
    assert plan.priority == "high"
    assert "PERSON" in plan.entity_types

@pytest.mark.asyncio
async def test_evidence_service_retrieval():
    """测试证据检索"""
    service = EvidenceService([MockKBProvider()])
    plan = InfoPlan(queries=["test"], entity_types=["*"], priority="high")
    
    evidence = await service.retrieve(plan)
    
    assert len(evidence.snippets) > 0
    assert evidence.confidence > 0

@pytest.mark.asyncio
async def test_agent_with_evidence():
    """测试 Agent 使用 evidence"""
    req = AgentRequest(
        obs=make_obs("Who is Alice?"),
        decision=GateDecision(...),
        state=SessionState("test"),
        now=datetime.now(timezone.utc),
        evidence=Evidence(
            snippets=["Alice is a person..."],
            sources=["KB"],
            confidence=0.9
        )
    )
    
    agent = DefaultAgentOrchestrator()
    resp = agent.handle(req)
    
    assert resp.success
    # 验证 response 中包含了 evidence 信息
```

---

### 风险与缓解

| 风险 | 缓解 |
|------|------|
| Evidence 检索超时卡住 worker | asyncio.wait_for() с 2s timeout |
| Evidence 信息过多，污染 prompt | 限制 snippet 数量、截断长度 |
| 错误 evidence 误导 LLM | 添加 confidence 信息，LLM 可选用 |
| 多个 provider 竞争资源 | 异步并发，不阻塞 IO |
| Configuration 太复杂 | 提供 default 配置，enable_evidence=false 时 noop |

---

## 小结：扩展方案对比

| 方案 | 侵入性 | 异步性 | 灵活性 | 推荐度 |
|------|--------|--------|--------|-------|
| **A: Gate 后插入 Evidence (推荐)** | ⭐ 最小 | ✅ 支持 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| B: 独立 Evidence Session | ⭐⭐⭐ 大 | ✅✅ 完全并发 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| C: Planner 中新增 EVIDENCE step | ⭐⭐ 中 | ❌ 同步串行 | ⭐⭐⭐ | ⭐⭐ |

---

**关键决策**：采用方案 A (Gate 后插入) 作为主线，保留方案 B 作为长期优化目标。

