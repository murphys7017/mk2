# MK2 路线图（当前版）

最后更新：2026-02-20

## 1. 当前状态

项目已具备稳定主链路：

1. `Adapter -> Bus -> Router -> Worker -> Gate -> Agent -> emit -> Bus`
2. System Reflex + Nociception 闭环可运行
3. Memory 已接入 Core 主流程（event/turn 持久化，fail-open）
4. 测试分层完整（offline / integration）

## 2. 已完成里程碑

### A. 基础主干

1. InputBus / SessionRouter / SessionState / Core worker
2. 多 session 隔离与串行语义
3. 会话 GC

### B. Gate 与系统反射

1. Gate pipeline（scene/feature/scoring/dedup/policy/finalize）
2. Drop/Sink/Deliver 分流
3. Gate 配置热更新
4. Nociception + System Reflex 保护回路

### C. Agent MVP

1. Planner / EvidenceRunner / Answerer / Speaker / PostProcessor 编排
2. fallback 机制
3. 防 Agent 回流自触发

### D. Memory 接入

1. Core 默认自动初始化 Memory（可关闭）
2. 入站 event 持久化
3. DELIVER 场景 turn 生命周期持久化
4. 失败队列上限、落盘、轮转、dead-letter
5. 关键路径测试覆盖补齐

### E. 文档治理

1. 文档主入口重组（`docs/README.md`）
2. 旧版 Memory 文档归档至 `docs/archive/memory/`
3. 新增统一测试文档（`docs/TESTING.md`）

## 3. 下一阶段

### F. Agent 能力增强（高优先级）

1. Evidence 真源接入（替换更多 stub）
2. Planner 策略配置化升级
3. Answerer provider 级重试/超时/降级策略

### G. 可观测性增强（中优先级）

1. 分阶段延迟指标（Gate/Agent/Memory）
2. 统一 trace_id 贯穿主链路
3. 关键保护动作结构化日志

### H. 结构治理（中优先级）

1. 拆分 `core.py`（worker orchestration / system handler）
2. 收敛模块边界，降低单文件复杂度

## 4. 执行建议

1. 每次迭代优先保证 `pytest -m "not integration"` 稳定。
2. integration 测试独立流水线执行并长期保活。
3. 文档以 Active 单文档策略维护，避免同主题并行漂移。
