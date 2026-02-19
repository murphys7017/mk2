# MK2

长期运行、多会话、可自保护的事件驱动 Agent 系统。

## 1. 当前能力

1. 主链路：`Adapter -> Bus -> Router -> Worker -> Gate -> Agent -> emit -> Bus`
2. Gate：规则化分流（DROP / SINK / DELIVER）与预算控制
3. System Reflex：基于 Nociception 的运行时自调节
4. Memory：已接入 Core 主流程（event/turn 持久化，默认启用，fail-open）
5. 测试：offline 与 integration 分层

## 2. 快速开始

```bash
# 安装依赖
uv sync

# 离线测试（推荐）
uv run pytest -m "not integration" -q

# 启动
uv run python main.py
```

## 3. 测试命令

```bash
# 全量（包含 integration）
uv run pytest -q

# 仅离线
uv run pytest -m "not integration" -q

# 仅集成（真实外部依赖）
uv run pytest -m integration -q
```

说明：
1. integration 中的 LLM provider 直连测试默认由 `RUN_LLM_LIVE_TESTS=1` 控制。
2. 可用 `uv run pytest -q -rs` 查看 skip 原因。

## 4. 配置文件

1. `config/gate.yaml`
2. `config/llm.yaml`
3. `config/memory.yaml`

建议使用环境变量注入密钥，避免明文提交。

## 5. 文档入口

1. `docs/README.md`（总索引）
2. `docs/DEPLOYMENT.md`（部署与运行）
3. `docs/TESTING.md`（测试策略）
4. `docs/MEMORY.md`（Memory 当前实现）
5. `docs/PROJECT_MODULE_DEEP_DIVE.md`（模块深潜）

## 6. 历史文档

旧版本文档已统一归档到 `docs/archive/`。
