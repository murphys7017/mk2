# Documentation Index

本文件是当前仓库文档入口，按“是否仍应维护”分组。

## Keep (Active)
- `README.md`：项目中文概览与快速入口。
- `README-EN.md`：项目英文概览。
- `docs/PROJECT_MODULE_DEEP_DIVE.md`：当前最完整、与代码对齐的模块级维护文档。
- `docs/GATE_COMPLETE_SPECIFICATION.md`：Gate 专项深度规范（保留作策略参考）。
- `docs/SYSTEM_REFLEX_SPECIFICATION.md`：SystemReflex 机制说明。
- `docs/DESIGN_DECISIONS.md`：关键架构决策记录（ADR 风格）。
- `docs/ROADMAP.md`：路线图（建议持续更新）。
- `docs/DEPLOYMENT.md`：部署/运行说明（建议持续更新）。
- `docs/demo_e2e.md`：CLI E2E 演示与调试文档。
- `docs/REPO_AUDIT_TODO.md`：本轮工程审计与修复跟踪。

## Archived (Historical / Duplicate / Prompt Artifacts)
以下文档已移到 `docs/archive/`，原因包括：
- 与现有主文档重复
- 明显基于旧状态（如旧测试统计、旧阶段结论）
- 属于一次性任务书/审查报告，长期维护价值低

已归档文件：
- `docs/archive/analysis/ARCHITECTURE_BLUEPRINT.md`
- `docs/archive/reports/DEMO_COMPLETION_REPORT.md`
- `docs/archive/reports/PROJECT_REVIEW.md`
- `docs/archive/reports/WORKFLOW_AUDIT.md`
- `docs/archive/legacy/ARCHITECTURE.md`
- `docs/archive/legacy/GATE_SPECIFICATION.md`
- `docs/archive/copilot/COPILOT_GATE_PLANNER_DEDUP_REFACTOR.md`
- `docs/archive/copilot/Copilot 任务书：痛觉系统（Nociception）.md`
- `docs/archive/notes/1.md`
- `docs/archive/notes/实现总结：Core v0 → v0.1 升级（完整版）.md`

## Suggested Maintenance Policy
- 架构类内容统一以 `docs/PROJECT_MODULE_DEEP_DIVE.md` 为主，不再新增平行“全量架构文档”。
- 若新增专题文档，建议“一个专题一个文件”，避免再出现同主题 2-3 份并行版本。
- 历史阶段性报告统一放 `docs/archive/reports/`，避免污染当前入口。
