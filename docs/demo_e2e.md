# E2E CLI Demo（实验文档）

最后更新：2026-02-23

## 状态说明

`tools/demo_e2e.py` 当前处于实验/重构中，不属于主线稳定运行基线。  
建议把本文件作为历史参考，而不是日常运行手册。

## 当前建议

1. 需要验证主链路时，优先使用 `uv run python main.py`。
2. 需要做回归时，优先跑 `pytest -m "not integration" -q`。
3. 如果要继续维护 CLI E2E，请先对齐 `src/agent` 当前接口（`AgentQueen`）与 `src/adapters/cli_adapter.py`。

## 计划中的整理方向

1. 迁移 demo 到当前 AgentQueen 接口。
2. 精简命令集合，仅保留可长期维护的输入指令。
3. 给 demo 增加独立测试，避免文档与脚本长期漂移。

## 历史备注

旧版文档中提到的分阶段 trace 输出、脚本参数和 orchestrator 名称，来自早期实现；与当前主干可能不一致。
