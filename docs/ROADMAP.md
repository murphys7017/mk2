# MK2 开发路线图（当前基线）

**最后更新**: 2026-02-12

---

## 1. 当前状态

项目已经从“基础骨架”进入“可维护可扩展”阶段，当前主干能力：
- 事件驱动主链路可稳定运行：`Adapter -> Bus -> Router -> Worker -> Gate -> Agent -> emit -> Bus`
- Gate 决策链路完整，支持预算配置化（`budget_thresholds` + `budget_profiles`）
- SystemReflex 与 Nociception 闭环已接入
- Agent Orchestrator MVP 可运行，支持组件注入与 fallback
- 测试分层已建立（`integration` marker 已注册）

---

## 2. 已完成里程碑

## Phase A: 基础设施（Done）
- InputBus / SessionRouter / SessionState / Core worker 基础链路
- 多 session 隔离与串行语义
- 会话 GC（idle sweep + worker/state 回收）

## Phase B: Gate 与系统反射（Done）
- Gate pipeline（scene/feature/scoring/dedup/policy/finalize）
- Drop/Sink/Deliver 分流与 pools
- GateConfigProvider 热加载（含 Windows mtime/hash 兜底）
- Nociception + SystemReflex 基本闭环

## Phase C: 稳定性专项（Done）
- 防 agent 回流自触发（loop guard）
- LLM 调用线程化，避免阻塞 asyncio loop
- 会话 GC 与 router remove 协同
- 用户消息安全阀（避免无意义沉默 sink）

## Phase D: 配置与可测试性（Done）
- budget 政策从硬编码迁移到 `config/gate.yaml`
- orchestrator 注入能力（便于测试与替换）
- 离线/在线测试策略拆分

---

## 3. 当前进行中（In Progress）

## Phase E: 文档与运维一致性收敛
目标：文档和代码行为持续一致，避免“文档可运行性漂移”。

正在做：
- 文档入口统一（`docs/README.md`）
- 历史/重复文档归档（`docs/archive/`）
- 部署与路线图改为当前基线描述

---

## 4. 下一阶段（Next）

## Phase F: Agent 能力增强（高优先级）
目标：在不破坏 Gate 边界的前提下提升认知能力。

建议顺序：
1. `Planner`：从规则启发式升级为可配置策略（保持预算约束）
2. `EvidenceRunner`：把 stub 源替换为真实可插拔 evidence providers
3. `Answerer`：完善 provider 级超时/重试/错误分级
4. `PostProcessor`：增加结构化审计事件与可观测埋点

验收建议：
- 每一项都先补离线测试，再加可选在线测试
- 新增能力不得绕过 GateHint 预算约束

## Phase G: 可观测性增强（中优先级）
目标：提升定位效率和线上可运维性。

建议项：
1. 增加 per-stage latency 指标（Gate/Agent 分开）
2. 增加统一 trace_id 贯穿 Adapter→Core→Agent→Emit
3. 对关键保护动作（cooldown/suppress/reload）输出结构化日志

## Phase H: 结构治理（中优先级）
目标：控制 `core.py` 膨胀，降低长期维护成本。

建议项：
1. 拆分 `core.py` 的 system handler 与 worker orchestration
2. 将调试打印抽象为可切换 logger/event hook
3. 明确模块 owner（Gate/Agent/SystemReflex/LLM）边界文档

---

## 5. 90 天执行建议

1. 先完成 Phase F 的 Planner/Evidence 真源接入（确保不破坏预算和回流防护）。
2. 再落地 Phase G 的核心观测项（至少 latency + trace_id）。
3. 最后执行 Phase H 的 Core 拆分重构（先小拆再大拆）。

---

## 6. 风险与约束

- 单 session worker 串行语义必须保留（避免 state 竞态）。
- 任何新能力都应通过 `Observation` 契约接入，不走隐藏 side-channel。
- 不应让 Agent 直接修改 Gate 配置；调节仍应通过 SystemReflex 入口。

---

## 7. 进度维护规则

建议每次迭代仅维护以下三处：
- 本文档状态区（Done/In Progress/Next）
- `docs/REPO_AUDIT_TODO.md` 的任务状态
- `docs/PROJECT_MODULE_DEEP_DIVE.md` 的实现细节

这样可以避免再次出现多份路线图并行失真。
