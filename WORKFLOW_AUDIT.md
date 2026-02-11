# WORKFLOW_AUDIT.md

> 目标：执行链路级别自检（基于真实代码），不新增功能。

---

## A. ASCII 执行流程图（真实链路）

```
CLI 输入
  │
  ▼
CliInputAdapter._process_command()
  │  └─ _inject_observation()  → Observation
  ▼
AsyncInputBus.publish_nowait()
  │
  ▼
SessionRouter.run()  (async for obs in bus)
  │  └─ resolve_session_key()
  │  └─ SessionInbox.put_nowait()
  ▼
Core._watch_new_sessions() → Core._ensure_worker()
  ▼
Core._session_loop(session_key)
  │  ├─ [WORKER:IN]
  │  ├─ GateContext 构造 + reload_if_changed()
  │  ├─ gate.handle() → GateOutcome
  │  ├─ emit → bus.publish_nowait()  (回流)
  │  ├─ ingest → gate.ingest()
  │  └─ decision.action 分支
  │       ├─ DROP → 终止（不进入下一层）
  │       ├─ SINK → 终止（不进入下一层）
  │       └─ DELIVER → _handle_observation()
  ▼
Core._handle_observation()
  ├─ system session → _handle_system_observation()
  └─ user session → _handle_user_observation()
```

---

## B. 阶段对照表（真实代码）

| 阶段 | 输入 | 输出 | 可能分支 | 是否已验证 | 备注 |
|---|---|---|---|---|---|
| CLI 输入 | 终端文本 | 指令字符串 | /quit /session /tick /alert /suggest /trace /text | ✅ | 入口：`CliInputAdapter._cli_loop()` |
| Adapter | 字符串 + 当前 session | `Observation` | CONTROL/SCHEDULE/ALERT/MESSAGE | ✅ | 入口：`_inject_observation()` |
| Bus | `Observation` | 入队/丢弃 | ok / dropped | ✅ | `AsyncInputBus.publish_nowait()` |
| Router | `Observation` | 入 per-session inbox | drop newest | ✅ | `SessionRouter.run()` |
| Worker | inbox.get() | GateOutcome | DROP/SINK/DELIVER | ✅ | `Core._session_loop()` |
| Gate | obs + ctx + wip | GateOutcome | DROP/SINK/DELIVER + emit/ingest | ✅ | `DefaultGate.handle()` |
| emit 回流 | `Observation` | 再次入队 | 可形成循环 | 🟡 | `Core._session_loop()` → `bus.publish_nowait()` |
| ingest | `Observation` | 入池 | drop/sink/tool | ✅ | `DefaultGate.ingest()` |
| system_reflex | CONTROL | emit CONTROL/ALERT | 可能二次流转 | 🟡 | `SystemReflexController.handle_observation()` |
| user layer | obs + decision | 仅日志/统计 | 无 | 🟡 | `Core._handle_user_observation()` 仅日志 |

---

## C. 真实调用顺序与数据结构

### 1️⃣ CLI → Adapter
- 调用链：
  - `CliInputAdapter._cli_loop()` → `_process_command()` → `_inject_observation()`
- 生成的 Observation 字段（来自 `cli_adapter.py`）：
  - `obs_type`, `session_key`, `actor`, `payload`, `evidence`, `metadata`, `timestamp`, `received_at`, `source_name`, `source_kind`
- 完整性评估：🟢
  - 字段齐全，`EvidenceRef` 已填 `raw_event_id`/`raw_event_uri`
  - 风险：`actor_type="cli"` 与 `Actor.actor_type` 的 Literal 约束不一致（类型层面）🟡
- Gate scene infer 预期：
  - `MessagePayload.text` 存在时可用于 `SceneInferencer` 与 `FeatureExtractor` ✅

### 2️⃣ Adapter → Bus
- 调用链：`AsyncInputBus.publish_nowait()`
- 是否真实入队：✅（队列未满时 `put_nowait`）
- 队列是否有消费者：✅（`SessionRouter.run()` 作为 async iterator 消费）
- queue_size 可获取性：✅（`_queue.qsize()` 可访问）

### 3️⃣ Bus → Router → Worker
- Router 是否启动：✅（`Core._startup()` 启动 `router.run()` task）
- Worker 是否启动：✅（`_watch_new_sessions()` 轮询新增 session）
- Worker 是否 await queue.get：✅（`SessionInbox.get()` 使用 `await`）
- 未 await 的后台任务：
  - CLI 输入 task（adapter 内部）🟡（正常设计，但需关注退出时取消）
  - Core 内部任务：router/watcher/gc/worker 均由 `_shutdown()` cancel + gather ✅

### 4️⃣ Worker → Gate
- ctx 构造字段：
  - `now`, `config`(snapshot), `system_session_key`, `metrics`, `session_state`, `system_health=None`
- config snapshot 是否实时：✅（`reload_if_changed()` 在每条 obs 前执行）
- 可能风险：若 config 文件缺失或 stat 失败，会频繁 warning 🟡

### 5️⃣ Gate Pipeline（真实顺序）
来自 [src/gate/pipeline/base.py](src/gate/pipeline/base.py)
1. `SceneInferencer`
2. `HardBypass`
3. `FeatureExtractor`
4. `ScoringStage`
5. `Deduplicator`
6. `PolicyMapper`
7. `FinalizeStage`

说明：
- 每个 stage 直接修改 `wip` ✅
- `HardBypass`/`Deduplicator` 可能 early action_hint（但仍继续执行后续 stage）🟡
- `emit` 在 `HardBypass` 里生成（痛觉 ALERT）
- `ingest` 通常在 `DefaultGate.handle()` fallback 时生成

### 6️⃣ GateOutcome 执行
- Worker 中处理顺序：
  - `emit` → `bus.publish_nowait()` 回流 ✅
  - `ingest` → `gate.ingest()` 入池 ✅
- 回流循环风险：
  - emit 的 obs 可能触发同一路径反复生成 emit 🟡

### 7️⃣ decision.action 分支
- DROP：`_session_loop` 直接 `continue` ✅
- SINK：`_session_loop` 直接 `continue` ✅
- DELIVER：调用 `_handle_observation()` ✅
  - decision 传递：✅（`_handle_observation(..., decision)`）
  - 下一层是否存在：🟡（`_handle_user_observation` 仅日志/统计，无实际处理）

### 8️⃣ system_reflex 路径
- 触发条件：system session + `ObservationType.CONTROL`
- 调用链：`_handle_system_observation()` → `SystemReflexController.handle_observation()`
- `update_overrides` 生效：✅（内存快照替换）
- TTL 是否自动恢复：🟡
  - 仅在有后续 CONTROL/ALERT 进入 system session 时触发 `_evaluate_suggestion_ttl`
  - 无后台定时器，不会“自动”在无系统事件时恢复
- 是否 emit `CONTROL(system_mode_changed)`：✅（条件满足时发出）
- CLI /suggest 兼容性：🟡
  - CLI 发送的是 `ControlPayload(kind="tuning_suggestion", data={force_low_model, ttl})`
  - system_reflex 期待 `suggested_overrides` + `ttl_sec`
  - 结果：`no_allowed_overrides`，不会更新 overrides

### 9️⃣ overrides 实际生效验证
- emergency_mode：✅（最高优先级，强制 SINK + low）
- force_low_model：✅（仅在 DELIVER 时生效）
- drop_sessions / deliver_sessions：✅（drop 优先于 deliver）
- drop_actors / deliver_actors：✅（drop 优先于 deliver）
- 更新路径：`SystemReflexController.handle_tuning_suggestion()` → `GateConfigProvider.update_overrides()`
- 覆盖风险：🟡
  - `GateConfigProvider.reload_if_changed()` 重新读取 YAML 可能覆盖内存 overrides

### 🔟 循环风险检测
- emit → requeue → emit：🟡
  - Gate 的 emit 可能再次触发 Gate（尤其是 ALERT/CONTROL）
  - 当前无去重/限流保护
- system_reflex emit → system_reflex：🟡
  - 生成 `tuning_applied` 与 `system_mode_changed` 也会再次进入 system_reflex
  - 目前逻辑仅触发 `_evaluate_suggestion_ttl`，不形成即时循环
- CONTROL(tuning_suggestion) 重复处理：🟡
  - 若 CLI 连续发送，会重复触发 update_overrides（受 cooldown 限制）
- reload_if_changed 高频触发：🟡
  - 每条 obs 都 stat 文件，可能在高频输入时产生 IO 压力

---

## D. 未实现 / 未触发 / 未连接的分支

- `GateContext.trace` 未设置，pipeline trace 回调未启用（仅定义，无实际使用）🟡
- `system_health` 在 GateContext 中为 `None`，HardBypass 的 overload guard 实际不可触发 🟡
- `DELIVER` 的“下一层处理”未实现，仅日志与统计 🟡
- `rules/` 目录未在 pipeline 中使用（目前规则来自 `GateConfig.rules`）🟡

---

## E. 与 PROJECT_REVIEW.md 不一致之处

1. Gate 管道级数不一致
   - 文档声称“12级”管道（含 8-12 预留）
   - 实际代码为 7 级（SceneInferencer + HardBypass + 5 stage）
   - 风险等级：🟡

2. Gate 文件规模
   - 文档称 `gate.py` 300+ 行
   - 实际 `gate.py` 明显更短
   - 风险等级：🟢（描述偏差，不影响执行）

3. 配置路径描述
   - 文档提到 `config/gate.yaml`
   - 项目中确有 `config/`，但同时存在 `configs/`，存在歧义
   - 风险等级：🟡（易造成配置修改误指向）

4. GateOutcome 文档字段
   - 文档使用 `reason: str`
   - 真实代码中 `GateDecision.reasons: List[str]`
   - 风险等级：🟡

5. “规则模块”描述
   - 文档强调 `rules/*` 的逻辑存在
   - 真实执行路径未引用 `rules/*`
   - 风险等级：🟡

---

## F. 风险等级总览（问题标注）

- 🟢 正常
  - Adapter → Bus → Router → Worker 链路真实可达
  - Gate pipeline 真实执行
  - overrides 优先级实现正确（drop 优先于 deliver）

- 🟡 潜在问题
  - CLI /suggest 与 system_reflex payload 结构不匹配
  - overrides 与配置热加载可能相互覆盖
  - DELIVER 后无真实处理层
  - GateContext.trace 未接入
  - system_health 未注入
  - emit 回流缺少循环防护

- 🔴 必须修复
  - （当前未发现必须立即修复项）

---

## G. 当前系统完整度评估（结构层面）

- 结构完整度：**中等（≈60%）**
  - 主链路已贯通（Adapter → Bus → Router → Worker → Gate）
  - 关键支路存在但未完全闭环（DELIVER 处理层、system_reflex 与 CLI 建议）

## 是否可进入下一阶段
- **可进入“最小可用演示阶段”**（链路可跑通）
- **不建议进入“策略/智能层强化阶段”**（DELIVER 后处理未就绪）

## 是否存在必须修复项
- **无强制必须修复项**（但有多项潜在问题需注意）

---

## 结束语

本报告仅基于当前真实代码路径进行审查，不补全未实现特性，不新增功能。建议优先统一 system_reflex payload 与 CLI /suggest 的字段结构，并确认 overrides 与热加载的期望行为。