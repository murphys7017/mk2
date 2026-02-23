# MK2 设计决策（ADR）

**最后更新**: 2026-02-21  
**定位**: 记录当前仍有效、且已在代码中落地的架构决策。

---

## 1. 使用说明

- 本文档只写“已决策且仍有效”的内容。
- 已归档/失效方案请看 `docs/archive/`。
- 需要查看实现细节时，优先对照 `docs/PROJECT_MODULE_DEEP_DIVE.md`。

---

## 2. ADR 列表（当前有效）

## ADR-001：统一事件模型使用 `Observation`

**状态**: Accepted  
**原因**:
- 适配器输入、Gate 决策中间态、Agent 输出、系统反射事件都需要统一协议。
- 降低模块耦合，避免每层自定义结构导致转换爆炸。

**决策**:
- 系统内跨模块传递统一使用 `src/schemas/observation.py::Observation`。
- 所有状态变化都通过 Observation 流转，不走隐藏 side-channel。

**影响**:
- 正向：模块边界清晰，测试和追踪统一。
- 代价：需要维护 payload 类型约束和字段一致性。

---

## ADR-002：采用“每会话一个串行 worker”

**状态**: Accepted  
**原因**:
- `SessionState` 及会话内流程需要顺序一致性。
- 不同会话之间希望并行处理，避免全局串行阻塞。

**决策**:
- 在 `Core` 中按 `session_key` 维护 worker task。
- 会话内串行、会话间并发。

**实现锚点**:
- `src/core.py::_watch_new_sessions`
- `src/core.py::_ensure_worker`
- `src/core.py::_session_loop`

**影响**:
- 正向：避免会话内并发写状态冲突。
- 代价：单会话慢任务会阻塞该会话后续消息。

---

## ADR-003：Gate 保持同步、快速、确定性

**状态**: Accepted  
**原因**:
- Gate 目标是反射层而非智能层，必须稳定可预测。
- 复杂或慢操作不应进入 Gate。

**决策**:
- Gate pipeline 由同步 stage 组成（scene/feature/scoring/dedup/policy/finalize）。
- Gate 只输出 `GateOutcome`（`decision + emit + ingest`），不直接调用 Agent。

**实现锚点**:
- `src/gate/pipeline/base.py`
- `src/gate/gate.py`
- `src/gate/types.py`

**影响**:
- 正向：决策路径可解释，调试简单。
- 代价：更复杂智能逻辑必须放到 Agent 层。

---

## ADR-004：配置热更新使用“快照替换 + stamp/hash 检测”

**状态**: Accepted  
**原因**:
- 运行时需要动态更新 Gate 配置。
- Windows 上仅靠 mtime 判定不稳定。

**决策**:
- `GateConfigProvider` 维护不可变快照引用。
- 变化检测使用 `mtime_ns + size`，必要时回退到文件 hash。
- reload 失败时保留旧快照（fail-safe）。

**实现锚点**:
- `src/config_provider.py::GateConfigProvider`

**影响**:
- 正向：热更新稳定性提升，读路径无锁且快速。
- 代价：每次更新会分配新配置对象。

---

## ADR-005：Gate 行为语义固定为 `DROP/SINK/DELIVER`

**状态**: Accepted  
**原因**:
- 必须明确区分“抛弃”“缓冲/忽略”“继续处理”，否则链路可观测性差。

**决策**:
- `DROP` / `SINK`：不进入后续业务处理。
- `DELIVER`：进入 `_handle_observation`，允许触发 Agent。
- `emit` 先回流 bus，`ingest` 进入 pool，二者解耦。

**实现锚点**:
- `src/core.py::_session_loop`
- `src/gate/gate.py::ingest`

**影响**:
- 正向：行为一致、测试容易覆盖。
- 代价：需要严格维护 action 分支契约。

---

## ADR-006：Agent 回流消息必须显式防循环

**状态**: Accepted  
**原因**:
- Agent emit 的消息重新进入 bus，如不防护可能自触发循环。

**决策**:
- 在用户分支处理前，跳过 agent 生成消息：
  - `source_name.startswith("agent:")` 或
  - `actor_id == "agent"`

**实现锚点**:
- `src/core.py::_handle_user_observation`

**影响**:
- 正向：避免 runaway loop。
- 代价：若未来要支持 agent-to-agent，需要新增白名单路由策略。

---

## ADR-007：LLM 同步网络调用必须线程化

**状态**: Accepted  
**原因**:
- provider 目前使用同步 HTTP 客户端（`urllib`）。
- 直接在 asyncio 协程里调用会阻塞事件循环。

**决策**:
- `LLMAnswerer.answer()` 内部通过 `asyncio.to_thread(...)` 执行 gateway 调用。

**实现锚点**:
- `src/agent/answerer.py::LLMAnswerer.answer`

**影响**:
- 正向：不阻塞 event loop。
- 代价：线程池资源受限时仍可能出现排队延迟。

---

## ADR-008：系统调节入口统一在 SystemReflex（白名单+TTL）

**状态**: Accepted  
**原因**:
- Agent 可以建议调节，但不能直接写 Gate 配置。
- 需要可恢复、可审计、可控。

**决策**:
- Agent 通过 CONTROL (`tuning_suggestion`) 提建议。
- SystemReflex 按白名单过滤、cooldown 防抖、TTL 自动回滚。
- 运行时配置修改通过 `GateConfigProvider.update_overrides()` 执行。

**实现锚点**:
- `src/system_reflex/controller.py`
- `src/system_reflex/types.py`

**影响**:
- 正向：控制平面集中，安全边界清晰。
- 代价：白名单扩展需要显式变更。

---

## ADR-009：短期运行态与池采用 in-memory，不做持久化保证

**状态**: Accepted  
**原因**:
- 当前目标是低复杂度、快速迭代。
- `SessionState` / sink/drop/tool pools 主要用于运行期决策与调试。

**决策**:
- `SessionState`、Gate pools、大部分 metrics 使用内存存储。
- 进程重启后不保证恢复历史状态。

**实现锚点**:
- `src/session_router.py`（`SessionState`）
- `src/gate/pool/*`
- `src/core.py`（metrics/state）

**影响**:
- 正向：实现简单、性能好。
- 代价：无跨重启历史，生产审计需外部日志/监控补齐。

---

## ADR-010：Egress 采用“worker 入队 + 后台 loop”并行输出

**状态**: Accepted  
**原因**:
- 直接在 worker 内 `await` 外部输出会引入阻塞，拖慢会话消费。
- 输出失败应 fail-open，不能影响主处理链路。

**决策**:
- worker 在 `state.record(obs)` 后仅执行 `_enqueue_egress(obs)`（非阻塞）。
- Core 启动独立 `_egress_loop` 后台 task 处理真实输出。
- 输出超时/异常记录 warning，不中断 worker。

**实现锚点**:
- `src/core.py::_enqueue_egress`
- `src/core.py::_egress_loop`
- `src/core.py::_startup` / `src/core.py::_shutdown`（egress task 生命周期）

**影响**:
- 正向：输出与会话处理并行，吞吐与稳定性更好。
- 代价：增加一个异步队列与后台任务，需要关注队列满时的丢弃策略。

---

## ADR-011：Output Adapter 支持按 `session_key` 路由

**状态**: Accepted  
**原因**:
- 不同会话可能对应不同输出终端（CLI/WebSocket/IM）。
- 需要在不改 Core 主链路的前提下灵活分流。

**决策**:
- `EgressHub` 支持 `session_adapters` 映射。
- 命中 `session_key` 时优先使用会话专属 adapter，否则回落到默认 adapters。

**实现锚点**:
- `src/adapters/output/hub.py::EgressHub`

**影响**:
- 正向：输出通道可按会话隔离，扩展成本低。
- 代价：路由配置复杂度上升，需避免同会话重复绑定导致重复输出。

---

## ADR-012：MESSAGE 标准路径默认 DELIVER（直通）

**状态**: Accepted  
**原因**:
- 当前交互目标优先“有回应”，减少用户消息被策略沉默。
- DROP 仍由 hard bypass / dedup / overrides 等高优规则兜底。

**决策**:
- 在 `PolicyMapper` 标准路径中，`obs_type == MESSAGE` 默认 `DELIVER`。
- 非 MESSAGE 场景保留阈值策略（`deliver_threshold/sink_threshold/default_action`）。

**实现锚点**:
- `src/gate/pipeline/policy.py::PolicyMapper.apply`

**影响**:
- 正向：用户感知更稳定，回复率更高。
- 代价：MESSAGE 场景下阈值策略作用减弱，需要通过上游 DROP 规则和系统保护控制成本。

---

## 3. 未决议题（Pending）

- 是否引入持久化 memory/state（数据库或向量库）。
- 是否将 provider 层改成原生异步 HTTP 客户端。
- 是否将 `core.py` 拆分为更细的 orchestration 子模块。
- 是否引入统一 trace_id 贯穿 Adapter->Gate->Agent->Emit。

---

## 4. 变更规则

当满足以下任一条件时，应更新本文档：
- 核心边界发生变化（如 Gate 直接调用 Agent）。
- 并发模型变化（如会话内不再串行）。
- 配置与控制平面变化（如去掉 SystemReflex 白名单）。

建议同时更新：
- `docs/PROJECT_MODULE_DEEP_DIVE.md`
- `docs/ROADMAP.md`
- 相关测试用例
