# Memory 子系统文档（当前版）

## 1. 定位

Memory 是当前主流程的持久化子系统，负责三类数据：

1. Event（Observation 级别事件）
2. Turn（Agent 调用轮次）
3. Markdown Vault（配置与知识文档）

当前实现遵循 `fail-open`：Memory 失败不会阻断 Core 主流程。

## 2. 主流程接入（已落地）

接入点在 `src/core.py`。

1. Core 默认启用 Memory：
   - `enable_memory=True`
   - `memory_config_path="config/memory.yaml"`
   - 未显式注入 `memory_service` 时自动初始化。
2. 入站事件持久化：
   - 每条非 system session Observation 在 Gate 决策后写入 Event。
   - 成功后写回 `obs.metadata["memory_event_id"]`。
3. Turn 持久化：
   - 仅在 `DELIVER + MESSAGE` 场景创建 Turn。
   - 仅当 `memory_event_id` 存在时创建 Turn。
4. Turn 完结：
   - Agent 成功：`status=ok`
   - Agent 异常或 error：`status=error`
5. Core 关闭时自动 `memory_service.close()`，确保缓冲区 flush。

## 3. 存储结构

### 3.1 关系库（`src/memory/backends/relational.py`）

默认由 SQLAlchemy 管理，支持 MySQL 与 SQLite。

核心表：

1. `events`
2. `turns`
3. `configs`
4. `knowledge`

`initialize()` 会自动建表（`Base.metadata.create_all(...)`）。

### 3.2 Markdown Vault（`src/memory/backends/markdown_hybrid.py`）

默认目录（受配置影响）：

1. `md/`：配置文档（如 system、users）
2. `knowledge/`：知识文档（experiences/facts）
3. `metadata.json`：文件摘要与同步状态

## 4. 失败队列与恢复

`MemoryService` 内置失败事件队列机制：

1. DB 写失败事件进入内存失败队列。
2. 失败队列有内存上限，超限分批落盘。
3. Dump 文件支持大小阈值轮转。
4. 超过最大重试次数进入 dead-letter 文件。
5. 启动时自动加载历史失败事件并重试。

对应配置在 `config/memory.yaml` 的 `failure_queue`。

## 5. 配置说明

主配置文件：`config/memory.yaml`

关键字段：

1. `database.dsn`
2. `database.pool_size`
3. `database.max_overflow`
4. `vault.root_path`
5. `vector.*`（可选）
6. `failure_queue.*`

注意：请根据环境修改 `database.dsn`，避免提交生产密钥。

## 6. 常用命令

```bash
# 离线回归（推荐）
uv run pytest -m "not integration" -q

# Memory 相关测试
uv run pytest tests/test_memory_service_offline.py tests/test_memory_config.py -q

# 重建 Memory 向量索引（若启用）
uv run python tools/memory_reindex.py reindex --config config/memory.yaml
```

## 7. 测试覆盖现状

已覆盖重点：

1. Event/Turn 基础读写
2. `plan=None` 与 JSON 字段反序列化稳定性
3. Event/Turn ID 唯一性
4. L1/L2 事件去重
5. 失败重试、队列上限、轮转
6. dead-letter 分支
7. Dump 落盘后重启加载
8. Core 与 Memory 接入关键分支（包含 append_event 失败保护）

## 8. 历史文档归档

旧版 memory 设计与阶段总结已归档到：`docs/archive/memory/`

后续请只维护本文件，避免多份 Memory 文档并行漂移。
