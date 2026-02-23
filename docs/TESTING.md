# 测试指南

最后更新：2026-02-23

## 1. 测试分层

项目使用两类测试：

1. `offline`：不依赖外部在线服务
2. `integration`：依赖真实外部服务（LLM/API/本地服务）

`tests/conftest.py` 已注册 `integration` marker，并支持 async 用例。

## 2. 常用命令

```bash
# 全量（包含 integration）
uv run pytest -q

# 只跑离线（本地默认）
uv run pytest -m "not integration" -q

# 只跑集成
uv run pytest -m integration -q

# 查看跳过原因
uv run pytest -q -rs
```

若本机 `uv run pytest` 有兼容问题，可直接用：

```bash
pytest -m "not integration" -q
```

## 3. 当前基线（2026-02-23）

在当前仓库快照执行 `pytest -m "not integration" -q`：

1. `71 passed`
2. `1 skipped`
3. `4 deselected`

## 4. 集成测试前置条件

### 4.1 Core + Agent + LLM

文件：`tests/test_core_agent_e2e_live.py`

要求：

1. `config/llm.yaml` 配置了可用 provider/model
2. 对应 API key 或本地服务可访问

### 4.2 LLM Provider 直连

文件：`tests/test_llm_providers.py`

要求：

1. 设置 `RUN_LLM_LIVE_TESTS=1`
2. provider 可访问（例如 bailian/ollama）

## 5. 常用定向命令

```bash
# Memory 相关
pytest tests/test_memory_service_offline.py tests/test_memory_config.py -q

# Gate 热加载与路由
pytest tests/test_gate_config_hot_reload.py tests/test_session_router.py -q

# Agent 规划与回退
pytest tests/test_agent_phase0.py tests/test_agent_hybrid_planner_phase1.py -q
```

## 6. CI 建议

1. PR 必跑：`pytest -m "not integration" -q`
2. integration 独立 Job 运行：`pytest -m integration -q`
3. 分离展示 offline 与 integration 结果，避免互相掩盖
