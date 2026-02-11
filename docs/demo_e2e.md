# E2E CLI Demo 文档

## 功能概述

**E2E CLI Demo** 是一个真实系统端到端演示脚本，用于验证完整的处理链路：
- 启动真实的 Core（InputBus/Router/Workers/Gate/ConfigProvider/SystemReflex）
- 通过交互式 CLI 注入 Observation
- 观察系统中每个关键节点的处理结果
- 验证 Gate→DELIVER 分支的数据传递

## 运行方式

### 基础启动

```bash
uv run python tools/demo_e2e.py
```

启动后，你会看到：

```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║  🎬 E2E Demo - 真实系统端到端演示                              ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

══════════════════════════════════════════════════════════════════
  🎬 E2E Demo CLI 已启动 (CLI Input Adapter)
══════════════════════════════════════════════════════════════════
支持的命令:
  <text>                              - 发送文本到当前 session
  /session <key>                      - 切换 session_key
  /tick                               - 注入 system tick
  /alert <kind>                       - 注入 ALERT (e.g., drop_burst)
  /suggest force_low_model=0|1 ttl=<sec> - 注入 tuning_suggestion
  /trace on|off                       - 开关 gate trace
  /quit                               - 退出
══════════════════════════════════════════════════════════════════

[session: demo] > 
```

## CLI 命令

### 1. 发送普通文本

```
[session: demo] > hello
[CLI] Sent text to session 'demo'
```

输出示例：
```json
[ADAPTER]
{
  "id": 1,
  "type": "tick",
  "session_key": "demo",
  "timestamp": "2026-02-11T10:30:45.123456+00:00"
}

[BUS]
{
  "queue_size": 1,
  "status": "published"
}

[WORKER:IN]
{
  "session_key": "demo",
  "obs_type": "tick",
  "source": "cli_input",
  "timestamp": "2026-02-11T10:30:45.123456+00:00"
}

[GATE:CTX]
{
  "session_key": "demo",
  "config_version": "unknown",
  "overrides": {
    "emergency_mode": false,
    "force_low_model": false
  },
  "timestamp": "2026-02-11T10:30:45.123456+00:00"
}

[GATE:OUT]
{
  "action": "deliver",
  "scene": "dialogue",
  "score": 0.85,
  "emit_count": 0,
  "ingest_count": 0,
  "reasons": ["score_based_routing"]
}

[DELIVER]
{
  "action": "DELIVER",
  "obs_type": "tick",
  "session_key": "demo",
  "decision_scene": "dialogue",
  "decision_reasons": ["score_based_routing"],
  "note": "此 Observation + Decision 将传递给下一层处理"
}
```

### 2. 切换 Session

```
[session: demo] > /session user123
[CLI] Switched to session: user123

[session: user123] > hello from user123
```

### 3. 注入 System Tick

```
[session: demo] > /tick
[CLI] Injected TICK to system session
```

### 4. 注入 Alert

```
[session: demo] > /alert drop_burst
[CLI] Injected ALERT: drop_burst
```

输出示例（Alert 进入 system session）：

```json
[ADAPTER]
{
  "id": 3,
  "type": "alert",
  "session_key": "system",
  "timestamp": "2026-02-11T10:31:15.654321+00:00"
}

[GATE:OUT]
{
  "action": "sink",
  "scene": "alert",
  "score": 0.0,
  "reasons": ["alert_scene", "sink_by_default"],
  "ingest_count": 1
}
```

### 5. 注入 Tuning Suggestion

```
[session: demo] > /suggest force_low_model=1 ttl=5
[CLI] Injected CONTROL(tuning_suggestion): {'force_low_model': True, 'ttl': 5}
```

预期行为：
- SystemReflex 接收到 CONTROL(tuning_suggestion)
- overrides 中 force_low_model 在接下来的请求中生效
- 5 秒后自动恢复为 false

验证：在 suggestion 后立即发送文本，应该看到 Gate output 中 model_tier 为 "low"

```
[session: demo] > hello
[GATE:OUT]
{
  "action": "deliver",
  "scene": "dialogue",
  "score": 0.85,
  "model_tier": "low",  ← force_low_model 已生效
  "reasons": ["force_low_model_override"]
}
```

### 6. 开关 Gate Trace

```
[session: demo] > /trace on
[CLI] Gate trace enabled

[session: demo] > hello
[GATE:TRACE:scene_inferencer]
{
  "stage": "scene_inferencer",
  "scene": "dialogue",
  "action_hint": null,
  "score": 0.0,
  "reasons": []
}

[GATE:TRACE:FeatureExtractor]
{
  "stage": "FeatureExtractor",
  "scene": "dialogue",
  "action_hint": null,
  "score": 0.0,
  "reasons": ["feature_extracted"]
}

[GATE:TRACE:ScoringStage]
{
  "stage": "ScoringStage",
  "scene": "dialogue",
  "action_hint": null,
  "score": 0.85,
  "reasons": ["scored"]
}

[GATE:TRACE:PolicyMapper]
{
  "stage": "PolicyMapper",
  "action_hint": "deliver",
  "score": 0.85,
  "reasons": ["score_based_routing"]
}

[GATE:TRACE:FinalizeStage]
{
  "stage": "FinalizeStage",
  "action_hint": "deliver",
  "reasons": ["finalized"]
}
```

### 7. 退出 Demo

```
[session: demo] > /quit
[CLI] /quit detected, shutting down...
[DEMO] ... 正在关闭 Core ...
```

## 验收标准

运行以下命令验证 Demo 功能：

```bash
uv run python tools/demo_e2e.py
```

然后依次输入这三条命令：

### 命令 1: 普通文本

```
hello
```

**验证点**:
- ✅ 看到 [ADAPTER] - Observation 已生成
- ✅ 看到 [BUS] - 已发布到队列
- ✅ 看到 [WORKER:IN] - Worker 已接收
- ✅ 看到 [GATE:OUT] - 包含 action=deliver/sink/drop
- ✅ 如果 action=DELIVER，看到 [DELIVER] 和 decision 信息

### 命令 2: 注入 Alert

```
/alert drop_burst
```

**验证点**:
- ✅ 看到 alert 进入 system session
- ✅ [GATE:OUT] 中 scene=alert
- ✅ 看到 [WORKER:INGEST] - alert 已入池

### 命令 3: Tuning Suggestion

```
/suggest force_low_model=1 ttl=5
```

**验证点**:
- ✅ 看到 CONTROL(tuning_suggestion) 被处理
- ✅ 接下来的请求中，[GATE:OUT] 显示 model_tier=low（如果 system_reflex 已集成）
- ✅ 5 秒后，新请求的 model_tier 恢复为 default

## 实现细节

### 可观测节点

Demo 会在以下位置打印结构化日志：

| 节点 | 标签 | 何时打印 | 包含信息 |
|------|------|--------|---------|
| Adapter | `[ADAPTER]` | 每个 Observation 生成时 | obs_type, session_key, timestamp |
| Bus | `[BUS]` | publish_nowait() 成功时 | queue_size, status |
| Worker Input | `[WORKER:IN]` | Worker 从 inbox 取出 obs 时 | session_key, obs_type, source |
| Gate Context | `[GATE:CTX]` | Gate.handle() 开始时 | config, overrides, timestamp |
| Gate Trace | `[GATE:TRACE:<stage>]` | 每个 stage 完成时（如果启用 trace） | stage_name, action, score, reasons |
| Gate Output | `[GATE:OUT]` | Gate.handle() 结束时 | action, scene, score, emit/ingest count |
| Deliver Branch | `[DELIVER]` | 当 decision.action==DELIVER 时 | obs + decision 信息（传递给下一层） |
| Worker Emit | `[WORKER:EMIT]` | Worker emit() 时 | obs_type, session_key, republish flag |
| Worker Ingest | `[WORKER:INGEST]` | Worker ingest() 时 | session_key, ingest_count |
| Loop Guard | `[LOOP_GUARD]` | Observation hop 超过 6 时 | reason, hop_count, max_hops |

### Gate Trace Hook 实现

如果启用 `/trace on`：

1. Demo 传递 `trace: Callable` 到 GateContext
2. Gate pipeline 每个 stage 完成后调用 `ctx.trace(stage_name, wip)`
3. trace 回调打印 `[GATE:TRACE:<stage>]` 日志

### LOOP_GUARD 实现

为了防止 emit→republish 陷入无限循环：

1. Observation.evidence 中增加 `hop` 计数
2. 每次 emit→republish 时，hop += 1
3. 若 hop > 6，Worker 打印 [LOOP_GUARD] 并丢弃该 obs

## 故障排查

### 问题：看不到 [GATE:TRACE] 输出

**原因**: Gate trace 默认关闭

**解决**: 输入 `/trace on` 启用

### 问题：看不到 model_tier 变化

**原因**: SystemReflex 可能未集成或 /suggest 命令参数错误

**解决**: 
1. 检查 Core 是否注入了 SystemReflex
2. 确认参数格式：`/suggest force_low_model=1 ttl=5`

### 问题：看不到 [DELIVER] 节点

**原因**: Gate 决策为 DROP/SINK，不走 DELIVER 分支

**解决**: 
1. 检查 Gate config（是否阈值过高）
2. 查看 [GATE:OUT] 中的 reasons 和 score 来诊断

## 设计决策

### 为什么用 CLI 而不是 HTTP 服务器？

- **交互性**：即时反馈，方便快速迭代
- **轻量化**：无需额外依赖或配置
- **可观测性**：可以直接打印详细日志

### 为什么不修改核心系统？

- **正交性**：Demo 完全通过现有接口集成（Adapter + CLI）
- **隔离性**：不涉及核心逻辑修改，仅在 GateContext 添加可选字段
- **可维护性**：Demo 代码与系统解耦，容易删除或升级

## 扩展方向

1. **HTTP 版本**: 将 CliInputAdapter 替换为 HttpInputAdapter
2. **Replay 模式**: 从日志文件重放 Observation 序列
3. **性能测试**: 添加并发压测模式
4. **可视化**: 将 trace 输出转换为 sequence diagram

---

**更新**: 2026-02-11  
**作者**: Copilot  
**状态**: 实验功能，用于开发和调试
