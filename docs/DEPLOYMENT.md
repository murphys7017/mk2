# AG99 部署与运行指南（原 MK2）

> 说明：历史名称为 MK2，标题保留以对齐旧资料。

最后更新：2026-02-23  
适用环境：Windows + Python 3.11+（推荐 `uv`）

## 1. 环境准备

```bash
cd d:\BaiduSyncdisk\Code\AG99
uv sync
```

若本机 `uv` 不可用，可直接使用本地 Python 环境安装依赖并运行 `pytest`。

## 2. 基线验证

### 2.1 离线回归（推荐第一步）

```bash
uv run pytest -m "not integration" -q
```

如果 `uv run pytest` 在本机报错，可回退：

```bash
pytest -m "not integration" -q
```

当前仓库快照（2026-02-23）离线回归结果：`71 passed, 1 skipped, 4 deselected`。

### 2.2 集成测试（依赖外部服务）

```bash
uv run pytest -m integration -q
```

说明：

1. 集成测试依赖真实 provider/API/本地服务。
2. `tests/test_llm_providers.py` live 直连用例受 `RUN_LLM_LIVE_TESTS=1` 控制。

## 3. 启动系统

```bash
uv run python main.py
```

## 4. 配置说明

### 4.1 Gate 配置（`config/gate.yaml`）

关键块：

1. `scene_policies`
2. `rules`
3. `drop_escalation`
4. `overrides`
5. `budget_thresholds`
6. `budget_profiles`

运行时热更新入口：`GateConfigProvider.reload_if_changed()`。

### 4.2 LLM 配置（`config/llm.yaml`）

1. 使用 `<ENV_VAR>` 注入密钥。
2. 避免提交明文密钥。

### 4.3 Memory 配置（`config/memory.yaml`）

1. Core 默认尝试初始化 Memory（`enable_memory=True`）。
2. 初始化失败时 fail-open，不阻断主流程。
3. 失败队列支持内存上限、落盘、轮转、dead-letter。

## 5. 运行时行为要点

1. 每个 session 一个串行 worker。
2. session 之间并发，session 内顺序执行。
3. `DELIVER + MESSAGE` 才会触发 Agent 主处理。
4. Agent 输出回灌 Bus，且通过回流保护避免自触发循环。
5. egress 通过独立队列/后台任务输出，避免阻塞 worker。

## 6. 已知事项

1. `tools/demo_e2e.py` 与 `docs/demo_e2e.md` 当前为实验链路，不是部署基线的一部分。
2. 生产/稳定环境建议以 `main.py` + Active 文档为准。

## 7. 相关文档

1. `docs/README.md`
2. `docs/TESTING.md`
3. `docs/MEMORY.md`
4. `docs/PROJECT_MODULE_DEEP_DIVE.md`
