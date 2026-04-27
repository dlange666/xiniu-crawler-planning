---
name: crawler-workflow-techdebt
description: 当任务是记录或管理 xiniu-crawler 仓库内非紧急后续事项时使用。本 skill 应用 AGENTS.md 中的技术债工作流，且不悄悄把债务推入活跃实现。
---

# Crawler Workflow · 技术债流

适用于：用户希望记录缺口、跟进事项或非紧急问题，但暂不立即实现。

## 首读顺序

按顺序加载：

1. `CLAUDE.md`
2. `AGENTS.md`
3. 暴露该债务的相关 plan / spec / 评估文件

跨仓库使用时，把"非紧急跟进登记"产物归属的角色映射为本工作流角色。

## 技术债流程

1. 把缺口登记到 `docs/exec-plan/tech-debt-tracker.md`。
2. 默认与活跃执行流隔离。
3. 未获用户显式批准之前，不要把债务移到 `docs/exec-plan/active/`、`docs/task/active/` 或代码实现。
4. 优先级变化且用户批准实现后，按正常流程建立 plan 与 task 记录，回到执行工作流。

## 默认姿态

- 把问题描述清楚。
- 不自动实现。
- 不把债务工作偷偷塞进无关任务。
- 把跟踪表保持简洁、可执行。
