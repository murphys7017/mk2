# 文档总览

本目录按“当前维护文档 / 历史归档文档”分层管理。

## 当前维护（Active）

1. `README.md`：项目中文总览（根目录）
2. `README-EN.md`：项目英文总览（根目录）
3. `docs/DEPLOYMENT.md`：部署与运行说明
4. `docs/TESTING.md`：测试分层与执行策略
5. `docs/MEMORY.md`：Memory 子系统（当前实现）
6. `docs/PROJECT_MODULE_DEEP_DIVE.md`：模块深潜说明
7. `docs/DESIGN_DECISIONS.md`：关键设计决策
8. `docs/GATE_COMPLETE_SPECIFICATION.md`：Gate 专项规范
9. `docs/SYSTEM_REFLEX_SPECIFICATION.md`：System Reflex 规范
10. `docs/demo_e2e.md`：E2E 工具使用说明
11. `docs/logging.md`：日志规范
12. `docs/ROADMAP.md`：路线图

## 历史归档（Archive）

统一放在 `docs/archive/`：

1. `docs/archive/legacy/`：旧架构/旧规范
2. `docs/archive/reports/`：阶段性报告
3. `docs/archive/notes/`：临时笔记
4. `docs/archive/copilot/`：一次性任务书与草案
5. `docs/archive/analysis/`：历史分析文档
6. `docs/archive/memory/`：旧版 Memory 设计与总结（已废弃）

## 维护规则

1. 同一主题只保留 1 份主文档。
2. 阶段性结论完成后转入 `docs/archive/`。
3. 代码行为变化必须同步更新对应 Active 文档。
4. 新文档命名尽量稳定，避免同主题并行（如 `*_v2`、`*_final2`）。
