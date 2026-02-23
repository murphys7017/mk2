# MK2 项目模块深潜文档（当前实现）

面向对象：准备长期维护、排障、扩展本仓库的工程同学。

基线时间：2026-02-21（与当前代码快照对齐）。

---

## 1. 先看全局：系统在做什么

这个仓库实现的是一个事件驱动的多会话 Agent runtime，核心思想是：

`Adapter -> Observation -> Bus -> Router -> Session Worker -> Gate -> Agent -> emit 回流 Bus -> Session Worker -> EgressQueue -> OutputAdapter`

其中：
- Gate 负责“快而硬”的门控（DROP/SINK/DELIVER + 预算 hint）。
- Agent 负责“慢而智能”的规划与回答。
- SystemReflex 负责系统级调节（例如临时 `force_low_model`）。

---

## 2. 运行时主链路（逐跳解释）

### 2.1 Adapter 层（输入生产者）

对应目录：`src/adapters/*`

- 被动型：`PassiveAdapter`（如 `TextInputAdapter`）。
- 主动型：`ActiveAdapter`（如 `TimerTickAdapter`）。
- 交互演示：`CliInputAdapter`。

统一行为：
- 所有 adapter 最终都调用 `BaseAdapter.emit(obs)`。
- `emit()` 失败时不会抛炸系统，而是尽量转成 `ALERT` 上报（生命体“喊疼”模型）。

### 2.2 Bus 层（异步总线）

文件：`src/input_bus.py`

- `publish_nowait(obs)`：同步、非阻塞投递（Adapter/Gate/Agent 都走这里）。
- `get()` / `__aiter__`：Router 异步消费。
- 满队列策略默认 `drop_when_full=True`，属于“保活优先”的丢新策略。

### 2.3 Router 层（按 session 分流）

文件：`src/session_router.py`

- `run()` 从 bus 拉 `Observation`，按 `resolve_session_key(obs)` 放入 `SessionInbox`。
- 每个 session 一个 FIFO inbox；inbox 满时 drop newest。
- Core 通过 `list_active_sessions()` 发现活跃会话并拉起 worker。

### 2.4 SessionWorker（每会话串行执行器）

文件：`src/core.py`，函数 `_session_loop(session_key)`

每条 obs 的处理顺序：
1. `await inbox.get()`（第一处 await 阻塞点）。
2. `state.record(obs)` 更新 `SessionState`。
3. `_enqueue_egress(obs)`（命中输出策略时，放入 egress 队列，非阻塞）。
4. `gate_config_provider.reload_if_changed()`。
5. `gate.handle(obs, gate_ctx)` 得到 `GateOutcome`。
6. 先执行 `outcome.emit -> bus`，再 `outcome.ingest -> gate pools`。
7. 若 action 为 `DROP/SINK`，本条消息到此结束。
8. 若 action 为 `DELIVER`，`await _handle_observation(...)` 进入业务处理（可能触发 Agent）。

### 2.5 Gate（门控与预算）

核心文件：
- `src/gate/gate.py`
- `src/gate/pipeline/*`
- `src/gate/config.py`
- `src/gate/types.py`

pipeline 固定顺序：
1. `SceneInferencer`
2. `HardBypass`
3. `FeatureExtractor`
4. `ScoringStage`
5. `Deduplicator`
6. `PolicyMapper`
7. `FinalizeStage`

输出：
- `GateDecision`：`action/scene/score/reasons/hint`。
- `GateOutcome`：`decision + emit + ingest`。

### 2.6 Core handler / AgentQueen

文件：`src/core.py`、`src/agent/queen.py`

`_handle_user_observation()` 关键逻辑：
- 先做防回流：`source_name.startswith("agent:")` 或 `actor_id == "agent"` 直接跳过，防止 agent 自激活循环。
- 仅当 `decision.action == DELIVER` 且 `obs_type == MESSAGE` 才构建 `AgentRequest`。
- `await self.agent_queen.handle(req)`（第二处关键 await，可能慢）。
- 将 `agent_outcome.emit` 回灌 bus。

Agent 编排顺序（当前实现）：
- `Planner -> ContextBuilder -> PoolRouter -> Aggregator -> Speaker`。
- 任一步异常会返回 fallback `AgentOutcome`，避免整链路沉默。

### 2.7 回流路径

- Agent 的回复是新的 `Observation(MESSAGE)`，`source_name="agent:speaker"`，重新进入 Bus/Router/Worker。
- 由于 Core 的回流防护，agent 消息不会再次触发 agent。

### 2.8 Egress（出站输出）

对应目录：`src/adapters/output/*`，核心调度在 `src/core.py`。

- `should_egress(obs)` 决定哪些 observation 需要对外输出。
- Worker 通过 `_enqueue_egress(obs)` 入队，不阻塞主链路。
- `_egress_loop()` 后台串行消费并调用 `EgressHub.dispatch(obs)`。
- `EgressHub` 支持按 `session_key` 路由到不同 output adapter。

---

## 3. 关键数据契约（必须统一理解）

### 3.1 Observation（系统内唯一事件）

文件：`src/schemas/observation.py`

关键字段：
- `obs_type`: `message/world_data/alert/control/schedule/system`
- `session_key`: 会话隔离键
- `actor`: `actor_id + actor_type`
- `source_name/source_kind`: 来源追踪
- `payload`: 强类型 payload（MessagePayload/AlertPayload/...）

最小约束：
- `source_name` 不能为空。
- 时间字段必须带 tz。
- MESSAGE 场景会写入质量标记（例如 `EMPTY_CONTENT`）。

### 3.2 SessionState（运行态，不是长期记忆）

文件：`src/session_router.py`（类：`SessionState`）

包含：
- `processed_total/error_total`
- `last_active_at`
- `recent_obs`（`deque(maxlen=20)`）

注意：
- 这个对象是 worker 串行修改的轻量状态，不等于 memory subsystem。

### 3.3 GateDecision / GateHint / BudgetSpec

文件：`src/gate/types.py`

- `GateAction`: `DROP/SINK/DELIVER`
- `Scene`: `DIALOGUE/GROUP/SYSTEM/TOOL_CALL/TOOL_RESULT/ALERT/UNKNOWN`
- `GateHint`: 给 Agent 的策略提示（model_tier、response_policy、budget）
- `BudgetSpec`: `time_ms/max_tokens/evidence_allowed/max_tool_calls/...`

### 3.4 AgentRequest / AgentOutcome

文件：`src/agent/types.py`

- `AgentRequest`: `obs + gate_decision + session_state + now (+gate_hint)`
- `AgentOutcome`: `emit + trace + error`

---

## 4. 模块逐层细解

## 4.1 `src/core.py`

职责：
- 组装 bus/router/gate/config_provider/system_reflex/agent_queen/egress。
- 管理 adapter 生命周期。
- 管理 session worker/watcher/gc/egress 四类后台任务。
- 管理系统会话（pain/tick/control）。

关键函数：
- `_startup()` / `_shutdown()`
- `_watch_new_sessions()`
- `_session_loop()`
- `_enqueue_egress()` / `_egress_loop()`
- `_handle_system_observation()` / `_handle_user_observation()`
- `_session_gc_loop()` / `_sweep_idle_sessions()` / `_gc_session()`

并发语义：
- 会话内串行，会话间并发。
- `LLMAnswerer` 调用已放到 `to_thread`，避免卡死事件循环。

## 4.2 `src/input_bus.py`

职责：
- 连接同步写入端和异步读取端。

关键点：
- `publish_nowait` 会调用 `obs.validate()`。
- 队列满时 drop，记录 `dropped_total`。
- `close()` 后，队列清空后异步迭代自然停止。

## 4.3 `src/session_router.py`

职责：
- 从总线取消息并分发到会话 inbox。

关键点：
- `resolve_session_key()` 在 `session_key` 缺失时根据类型和 actor 补全。
- `remove_session()` 是 GC 成功后的必要动作，否则 watcher 会继续认为 session 活跃。

## 4.4 `src/session_router.py::SessionState`

职责：
- 提供可测试、可观测的会话最小运行态。

当前边界：
- 不负责持久化，不负责跨会话查询，不负责复杂 memory 检索。

## 4.5 `src/config_provider.py` / `src/core/config_provider.py`

职责：
- 提供 GateConfig 快照。
- 热加载 YAML 并支持运行时 override 更新。

实现特点：
- `reload_if_changed()` 采用 `mtime_ns + size`，且在 stamp 不变时额外比较 hash，规避 Windows mtime 粒度问题。
- `src/core/config_provider.py` 现在是薄封装重导出，避免重复实现。

## 4.6 `src/gate/*`

`config.py`：
- GateConfig 结构化配置对象。
- 已支持 `budget_thresholds` 和 `budget_profiles`，`select_budget(score, scene)` 按配置出预算。

`gate.py`：
- Gate 入口，调用 pipeline，补齐 fallback outcome。
- `ingest()` 按 action/scene 将 obs 放入 sink/drop/tool pool。

`scene.py`：
- 由 `ObservationType + MessagePayload` 快速推断场景。

`metrics.py`：
- Gate 侧处理计数（processed/by_scene/by_action）。

`pipeline/policy.py` 重点：
- 用户 MESSAGE + actor_type=`user` 时有 safety valve，避免被沉默 SINK（除硬 DROP）。
- 标准路径对 MESSAGE 默认 DELIVER（直通），非 MESSAGE 仍走阈值策略。
- override 优先级清晰，且 deliver override 不作用于 agent 生成消息。
- 输出 `GateHint` 给 Agent 预算约束。

## 4.7 `src/system_reflex/*`

职责：
- 处理 system CONTROL/ALERT 相关反射逻辑。

当前实现：
- 支持 `tuning_suggestion`。
- 白名单限制 agent 只能改允许字段（默认 `force_low_model`）。
- 支持 TTL 自动回滚 + cooldown 防抖。

## 4.8 `src/nociception.py`

职责：
- 统一 pain alert 结构。
- 提供痛觉聚合 key/severity 提取。

与 Core 配合：
- `_on_system_pain()` 聚合痛觉并触发 adapter cooldown/fanout suppress。
- `_on_system_tick()` 监测 drop 激增并产生系统 pain。

## 4.9 `src/agent/*`

`queen.py`：
- 当前 agent 编排入口（`AgentQueen.handle`）。
- 默认链路：`Planner -> ContextBuilder -> PoolRouter -> Aggregator -> Speaker`。
- 默认 Speaker 产出 `source_name="agent:speaker"`、`actor_id="agent"` 的 MESSAGE observation。

`types.py`：
- 定义 `AgentRequest` / `AgentOutcome` 等编排契约。

## 4.10 `src/llm/*`

`config.py`：
- 读取 `config/llm.yaml`。
- 仅支持整字段 `<ENV_VAR>` 占位符替换。

`client.py`：
- `LLMGateway` 统一 provider/model/params 调用接口。

`registry.py`：
- provider 工厂注册（目前 `bailian`、`ollama`）。

`providers/*`：
- 目前都是同步 `urllib` HTTP 客户端。
- 上层必须异步线程化调用，避免阻塞 asyncio loop。

---

## 5. 控制点与阻塞点地图

高频 await 点：
- `Core.run_forever -> await _router_task`
- `Core._session_loop -> await inbox.get()`
- `Core._handle_user_observation -> await agent_queen.handle(req)`
- `Core._egress_loop -> await egress.dispatch(obs)`
- `AgentQueen.handle -> await planner/build/run/postprocess`

潜在阻塞风险：
- provider HTTP 慢/超时会占用线程池 worker（不再阻塞 event loop，但会拖慢响应）。
- 单 session worker 串行，某条慢请求会阻塞该 session 后续消息。

回流循环控制：
- Core 在用户处理分支显式跳过 `agent:*` / `actor_id=agent` 消息。

---

## 6. 配置体系（Gate + LLM）

## 6.1 `config/gate.yaml`

关键块：
- `scene_policies`
- `rules`
- `drop_escalation`
- `overrides`
- `budget_thresholds`
- `budget_profiles`

生产维护建议：
- 改配置优先，不要先改代码硬编码阈值。
- 观察 `PolicyMapper` 和 `select_budget` 一致性。

## 6.2 `config/llm.yaml`

关键块：
- `default.provider`
- `providers.<name>.api_*`
- `providers.<name>.models.<model>`

安全注意：
- 推荐 `api_key: "<ENV_VAR>"`，不要明文提交密钥。
- 解析器对未设置环境变量会抛错，属于 fail-fast 行为。

---

## 7. 测试分层与建议命令

当前测试分布：
- Core/Router/GC：`tests/test_core_*.py`, `tests/test_session_*.py`
- Gate：`tests/test_gate_*.py`
- Agent 编排：`tests/test_agent_orchestrator_mvp.py`
- LLM：`tests/test_llm_*.py`
- SystemReflex/Nociception：`tests/test_system_reflex_*.py`, `tests/test_nociception_v0.py`

建议命令：
- 离线主回归：
  - `uv run pytest -m "not integration" -q`
- 在线 LLM 用例：
  - `$env:RUN_LLM_LIVE_TESTS="1"`（PowerShell）
  - `uv run pytest -m integration -q`
- Gate 热加载与 GC 定向：
  - `uv run pytest tests/test_gate_config_hot_reload.py tests/test_session_gc.py -q`

---

## 8. 扩展指南（低风险路径）

新增 Adapter：
1. 继承 `PassiveAdapter` 或 `ActiveAdapter`。
2. 只做 raw->Observation 变换，决策逻辑不要放 adapter。
3. 通过 `core.add_adapter()` 注入。

新增 Gate 规则：
1. 在 `pipeline` 新增 stage，保持 `apply(obs, ctx, wip)` 纯输入输出风格。
2. 明确 stage 顺序影响，更新 `PipelineRouter`。
3. 配套新增单测覆盖至少一条正路径和一条边界路径。

新增 Evidence 源：
1. Planner 加 source 规划逻辑。
2. EvidenceRunner 实现 source 拉取。
3. 在 budget（`evidence_allowed`, `max_tool_calls`）内运行。

新增 LLM Provider：
1. 实现 `call(messages, model, params)`。
2. 在 `registry.PROVIDERS` 注册。
3. 在 `llm.yaml` 增加 provider/models 配置和测试。

---

## 9. 维护者常见排障路径

现象：用户发消息无回复。
排查：
1. 看 `[ADAPTER]` 是否有输入。
2. 看 `[WORKER:IN]` 是否收到。
3. 看 `[GATE:OUT] action` 是否 `sink/drop`。
4. 看对应 session worker 是否存活。
5. 看 agent fallback 是否触发（`agent_error`）。

现象：会话越跑越卡。
排查：
1. 看是否单会话出现慢 LLM 调用堆积。
2. 看 `bus.dropped_total` 与 router `dropped_total`。
3. 看 pain/drop burst 指标是否持续触发 suppress。

现象：改了 gate.yaml 不生效。
排查：
1. 观察 `reload_if_changed()` 返回值。
2. 检查 YAML 是否可解析。
3. 确认文件内容确实变化（而非仅编辑后复原）。

---

## 10. 一句话总结

当前项目已经具备“可运行 + 可测试 + 可热调 + 可保护”的事件驱动 Agent 主干；后续演进重点不在“堆更多逻辑”，而在保持 Gate/Agent/SystemReflex 三层边界清晰，并持续把新能力收敛到统一 `Observation` 契约下。
