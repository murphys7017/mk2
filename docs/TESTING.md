# 测试指南

## 1. 测试分层

项目使用两类测试：

1. `offline`：不依赖外部在线服务
2. `integration`：依赖真实外部服务（LLM/API/本地服务）

`tests/conftest.py` 已注册 marker，并支持 async 用例兜底执行。

## 2. 常用命令

```bash
# 全量（包含 integration）
uv run pytest -q

# 只跑离线（推荐本地默认）
uv run pytest -m "not integration" -q

# 只跑集成
uv run pytest -m integration -q

# 查看 integration 用例列表
uv run pytest -m integration --collect-only -q
```

## 3. 当前基线（2026-02-20）

在当前仓库状态下：

1. `uv run pytest -q`：`74 passed, 1 skipped`
2. 当前 skip 来源：`tests/test_llm_providers.py`（未设置 `RUN_LLM_LIVE_TESTS=1`）
3. `-m "not integration"`：通过

## 4. 集成测试前置条件

### 4.1 Core + LLM E2E

文件：`tests/test_core_agent_e2e_live.py`

要求：

1. `config/llm.yaml` 存在可用 provider/model
2. 对应 API Key 或本地服务（如 Ollama）可用

### 4.2 LLM Provider 直连

文件：`tests/test_llm_providers.py`

要求：

1. 设置 `RUN_LLM_LIVE_TESTS=1` 才会执行 live 直连测试
2. `bailian` provider 可访问
3. `ollama` provider 可访问（若配置启用）

## 5. Memory 相关推荐命令

```bash
# Memory 离线测试（服务层 + 配置层）
uv run pytest tests/test_memory_service_offline.py tests/test_memory_config.py -q

# Core 与 Memory 接入分支
uv run pytest tests/test_core_orchestrator_injection.py tests/test_core_memory_autoinit.py -q
```

## 6. CI 建议

1. PR 必跑：`pytest -m "not integration" -q`
2. 夜间任务或专门流水线：`pytest -m integration -q`
3. 集成失败不应掩盖离线回归结果，建议分 Job 展示。
