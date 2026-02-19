# MK2 部署与运行指南（当前基线）

最后更新：2026-02-20  
适用环境：Windows + `uv` + Python 3.11+

## 1. 环境准备

```bash
cd d:\BaiduSyncdisk\Code\mk2
uv sync
uv run pytest --version
```

依赖以 `pyproject.toml` 为准。

## 2. 基线验证

### 2.1 离线回归（推荐第一步）

```bash
uv run pytest -m "not integration" -q
```

说明：

1. 不依赖外部在线服务。
2. 当前基线（2026-02-20）：通过。

### 2.2 集成测试（真实外部依赖）

```bash
uv run pytest -m integration -q
```

说明：

1. `tests/test_llm_providers.py` 的 live 直连用例默认受 `RUN_LLM_LIVE_TESTS=1` 控制。
2. 若本机/CI 未准备好 provider、API key 或本地服务，集成测试会失败或被跳过。

## 3. 启动系统

### 3.1 常规启动

```bash
uv run python main.py
```

### 3.2 E2E 演示

```bash
uv run python tools/demo_e2e.py
```

详细参数见 `docs/demo_e2e.md`。

## 4. 配置说明

### 4.1 Gate 配置（`config/gate.yaml`）

关键块：

1. `scene_policies`
2. `rules`
3. `drop_escalation`
4. `overrides`
5. `budget_thresholds`
6. `budget_profiles`

热加载：Worker 在处理 observation 时调用 `GateConfigProvider.reload_if_changed()`。

### 4.2 LLM 配置（`config/llm.yaml`）

建议：

1. 使用 `<ENV_VAR>` 占位符注入密钥。
2. 避免提交明文密钥。

### 4.3 Memory 配置（`config/memory.yaml`）

当前行为：

1. Core 默认尝试自动初始化 Memory（`enable_memory=True`）。
2. Memory 初始化失败时 fail-open，不阻断 Core 启动。
3. Memory 默认支持失败队列落盘、轮转、dead-letter。

## 5. 运行时行为要点

1. 每个 session 一个串行 worker。
2. system session 与普通用户 session 隔离。
3. `DELIVER + MESSAGE` 才会触发 Agent 主处理。
4. Memory 在主流程中执行 event/turn 持久化，但失败不阻断回复。

## 6. 生产检查清单

1. `uv sync` 成功。
2. `pytest -m "not integration"` 通过。
3. `config/gate.yaml`、`config/llm.yaml`、`config/memory.yaml` 可解析。
4. 外部服务密钥通过环境变量注入。
5. 启动后可观察到 worker/gate/agent/memory 关键日志。

## 7. 相关文档

1. `docs/README.md`
2. `docs/TESTING.md`
3. `docs/MEMORY.md`
4. `docs/PROJECT_MODULE_DEEP_DIVE.md`
