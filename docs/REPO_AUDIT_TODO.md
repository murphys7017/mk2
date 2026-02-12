# Repo Audit TODO 与处理方案

> 目标：优先解决“不通 / 卡死 / 沉默 / 难测 / 难扩展”的结构性问题。  
> 状态约定：`TODO` / `IN_PROGRESS` / `DONE` / `BLOCKED`

## 执行原则
- 先 P0，后 P1/P2。
- 每次只改 1-2 个点，改完立刻跑回归。
- 默认先做离线可测改造（stub），最后再跑在线集成。

## P0（必须先做）

### 1. 防回流循环失效（高风险）
- 状态：`TODO`
- 现象：agent 自己发出的消息会再次触发 agent，可能形成高频循环。
- 根因：`src/core.py` 用 `actor_type == "agent"` 防循环，但 `src/agent/speaker.py` 发的是 `actor_type="system"`。
- 最小方案：
  - 在 `src/core.py::_handle_user_observation` 改为来源防循环：`source_name.startswith("agent:")` 或 `actor_id == "agent"` 直接跳过。
  - 在 `src/gate/pipeline/policy.py` 的 deliver override 上，排除 agent 源消息。
- 变更点：
  - `src/core.py::_handle_user_observation`
  - `src/gate/pipeline/policy.py::PolicyMapper.apply`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_core_agent_e2e_live.py -q`
  - 新增回归：`uv run pytest -p no:cacheprovider tests/test_core_no_agent_loop.py -q`
- 验收标准：
  - 同一 session 下，agent emit 后不会再次触发 agent 处理链。

### 2. LLM 同步网络调用阻塞事件循环（高风险）
- 状态：`TODO`
- 现象：worker/session_loop 可能被网络 IO 卡住，GC/路由也被拖慢。
- 根因：`LLMAnswerer.answer` 是 async，但内部同步 `_gateway.call()` -> `urlopen(timeout=60)`。
- 最小方案：
  - 在 `src/agent/answerer.py::LLMAnswerer.answer` 用 `await asyncio.to_thread(...)` 包裹 `_gateway.call`。
- 变更点：
  - `src/agent/answerer.py::LLMAnswerer.answer`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_session_gc.py -q`
  - `uv run pytest -p no:cacheprovider tests/test_nociception_v0.py -q`
- 验收标准：
  - 在慢网络/失败网络时，不阻塞其他 session 的基本推进。

### 3. Session GC 后不会自动复活 worker（高风险）
- 状态：`TODO`
- 现象：session 被 GC 后，再来同 session 消息进入 inbox 但无 worker 消费。
- 根因：watcher 只为“新 session”启动 worker，router active session 不会清理。
- 最小方案：
  - `src/core.py::_watch_new_sessions` 改为每轮对 `current_sessions` 全量调用 `_ensure_worker`。
  - `_ensure_worker` 防御 task done 的情况并重建。
- 变更点：
  - `src/core.py::_watch_new_sessions`
  - `src/core.py::_ensure_worker`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_session_gc.py -q`
  - 新增回归：`uv run pytest -p no:cacheprovider tests/test_session_gc_reactivate.py -q`
- 验收标准：
  - 被 GC 的 session 再次收到消息后可恢复消费。

### 4. 沉默黑洞（CLI 输入被识别为非 user）
- 状态：`TODO`
- 现象：部分用户消息可能不触发 user safe valve，导致 SINK/DROP 后无回复。
- 根因：`src/adapters/cli_adapter.py` 注入 `actor_type="cli"`，但 policy safe valve 仅匹配 `actor_type="user"`。
- 最小方案：
  - 将 CLI 注入 actor_type 改为 `"user"`（或 policy 扩展兼容 `cli`）。
- 变更点：
  - `src/adapters/cli_adapter.py::_inject_observation`
  - 可选：`src/gate/pipeline/policy.py`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_gate_worker_integration.py -q`
  - `uv run pytest -p no:cacheprovider tests/test_core_metrics.py -q`
- 验收标准：
  - CLI 用户消息与 TextInput 用户消息行为一致。

## P1（稳定性与可维护性）

### 5. Gate 热加载在 Windows 上判定不稳
- 状态：`TODO`
- 现象：配置变更后偶发不 reload。
- 根因：`reload_if_changed` 仅看 `st_mtime`。
- 最小方案：
  - 改为 `(st_mtime_ns + st_size)`，必要时补内容哈希兜底。
- 变更点：
  - `src/config_provider.py`
  - （同步清理重复实现）`src/core/config_provider.py`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_gate_config_hot_reload.py -q`

### 6. Core 默认依赖 live LLM（难测）
- 状态：`TODO`
- 现象：单测/本地运行容易受外网与密钥影响。
- 根因：`Core` 默认 `DefaultAgentOrchestrator()`，其默认 `LLMAnswerer(bailian)`。
- 最小方案：
  - `Core.__init__` 增加可注入 `agent_orchestrator`。
  - 测试默认注入 stub answerer / stub orchestrator。
- 变更点：
  - `src/core.py::__init__`
  - `tests/*`（按需注入）
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_session_gc.py -q`
  - `uv run pytest -p no:cacheprovider tests/test_agent_orchestrator_mvp.py -q`

### 7. pytest `integration` marker 未注册
- 状态：`TODO`
- 现象：运行集成测试有 `PytestUnknownMarkWarning`。
- 最小方案：
  - 在 `pyproject.toml` 的 `tool.pytest.ini_options` 中注册 `integration` marker。
- 变更点：
  - `pyproject.toml`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_core_agent_e2e_live.py -q`

### 8. 测试固定 sleep 导致抖动
- 状态：`TODO`
- 现象：不同机器/负载下不稳定。
- 最小方案：
  - 用 polling + timeout 替换固定 `sleep`（复用 wait_until helper）。
- 变更点：
  - `tests/test_session_gc.py`
  - `tests/test_core_metrics.py`
  - `tests/test_gate_config_hot_reload.py`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_session_gc.py tests/test_core_metrics.py tests/test_gate_config_hot_reload.py -q`

## P2（结构整理）

### 9. 重复模块清理
- 状态：`TODO`
- 现象：`src/config_provider.py` 与 `src/core/config_provider.py` 重复。
- 最小方案：
  - 统一单一实现，删除或弃用另一份。
- 验证命令：
  - `uv run pytest -p no:cacheprovider -q`

### 10. Gate 预算配置与代码硬编码不一致
- 状态：`TODO`
- 现象：`config/gate.yaml` 有 `budget_thresholds/budget_profiles`，代码未读取。
- 最小方案：
  - 先在文档中明确“当前未生效”；后续按需接入配置读取。
- 变更点：
  - `src/gate/config.py`
  - `src/gate/pipeline/policy.py`
- 验证命令：
  - `uv run pytest -p no:cacheprovider tests/test_gate_mvp.py -q`

---

## 建议实施顺序（供审阅）
1. 第 1 批：P0-1 + P0-4（先止循环与沉默）
2. 第 2 批：P0-2 + P0-3（解除阻塞并修复 GC 复活）
3. 第 3 批：P1-5 + P1-7 + P1-8（稳定性）
4. 第 4 批：P1-6 + P2-9 + P2-10（可维护性）

## 测试分层建议
- 离线默认：`uv run pytest -p no:cacheprovider -m "not integration" -q`
- 在线按需：`$env:RUN_LLM_LIVE_TESTS="1"; uv run pytest -p no:cacheprovider -m integration -q`

## 审阅记录
- [ ] 你确认实施顺序
- [ ] 你确认第 1 批改造范围
- [ ] 开始逐步实施
