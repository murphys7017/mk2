# MK2 部署与运行指南（当前基线）

**最后更新**: 2026-02-12  
**适用环境**: Windows + `uv` + Python 3.11+

---

## 1. 环境准备

```bash
# 在项目根目录
cd d:\BaiduSyncdisk\Code\mk2

# 安装依赖
uv sync

# 验证 pytest 可用
uv run pytest --version
```

依赖以 `pyproject.toml` 为准。

---

## 2. 先做基线验证

### 2.1 离线回归（推荐第一步）

```bash
uv run pytest -p no:cacheprovider -m "not integration" -q
```

说明：
- 该命令不跑 live 外部服务用例。
- 2026-02-12 最近一次基线结果：`46 passed, 4 deselected`。

### 2.2 在线/集成用例（可选）

```bash
# Windows PowerShell
$env:RUN_LLM_LIVE_TESTS="1"
uv run pytest -p no:cacheprovider -m integration -q
```

说明：
- 需要可用的 LLM provider 和 API 配置。
- 若不具备外部条件，可跳过。

---

## 3. 启动系统

### 3.1 常规启动

```bash
uv run python main.py
```

### 3.2 E2E CLI 演示

```bash
uv run python tools/demo_e2e.py
```

详细命令说明见 `docs/demo_e2e.md`。

---

## 4. 配置说明

## 4.1 Gate 配置（`config/gate.yaml`）

关键块（当前实现已生效）：
- `scene_policies`
- `rules`
- `drop_escalation`
- `overrides`
- `budget_thresholds`
- `budget_profiles`

热加载：
- Worker 在处理 observation 时调用 `GateConfigProvider.reload_if_changed()`。
- 判定逻辑为 `mtime_ns + size`，必要时回退 `hash` 比较，兼容 Windows mtime 粒度问题。

## 4.2 LLM 配置（`config/llm.yaml`）

建议：
- `api_key` 使用 `<ENV_VAR>` 占位符，不要明文写入密钥。
- 例如：`api_key: "<BAILIAN_API_KEY>"`。

占位符解析规则：
- 仅支持整字段占位符（完整形态 `<ENV_VAR>`）。
- 未设置环境变量会报错（fail-fast）。

---

## 5. 常用运行参数（`Core`）

`src/core.py` 当前构造参数（节选）：

```python
core = Core(
    bus_maxsize=1000,
    inbox_maxsize=256,
    enable_session_gc=True,
    idle_ttl_seconds=600,
    gc_sweep_interval_seconds=30,
    min_sessions_to_gc=1,
)
```

说明：
- 会话 GC 由 `enable_session_gc + idle_ttl_seconds + gc_sweep_interval_seconds` 控制。
- 每个 session 一个串行 worker；session 间并发。

---

## 6. 生产检查清单

- [ ] `uv sync` 成功。
- [ ] 离线测试通过（`-m "not integration"`）。
- [ ] `config/gate.yaml`、`config/llm.yaml` 可解析。
- [ ] API 密钥通过环境变量注入，不在仓库明文。
- [ ] 启动后能看到 worker/gate 日志并处理用户消息。

---

## 7. 故障排查速查

### 7.1 用户消息无回复
1. 看 Adapter 是否有输入日志。
2. 看 `[WORKER:IN]` 是否收到。
3. 看 `[GATE:OUT] action` 是否为 `sink/drop`。
4. 看 session worker 是否存活。
5. 看是否触发了 agent fallback（`agent_error`）。

### 7.2 修改 gate.yaml 不生效
1. 检查 YAML 语法。
2. 观察 `reload_if_changed()` 是否触发。
3. 确认文件内容确实发生变化。

### 7.3 会话堆积/延迟高
1. 观察单 session 是否被慢请求阻塞（worker 串行语义）。
2. 检查 bus/router drop 指标。
3. 检查是否频繁触发 pain/drop burst 抑制策略。

---

## 8. 相关文档

- `docs/README.md`（文档总入口）
- `docs/PROJECT_MODULE_DEEP_DIVE.md`（模块深潜）
- `docs/DESIGN_DECISIONS.md`（设计决策）
- `docs/demo_e2e.md`（E2E CLI）
