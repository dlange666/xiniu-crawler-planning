# 执行计划模板

用于 `docs/exec-plan/active/` 下的活跃实施计划。

## 1. 元信息

- **Plan ID**：`plan-YYYYMMDD-<slug>`
- **关联规格**：`docs/prod-spec/<spec-name>.md`
- **状态**：`active | completed | suspended`
- **负责角色**：`Planner`

## 2. 目标

本计划达成的事，以及它如何对应产品规格中的成功标准。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-YYYYMMDD-101 | … | `<spec>.md §<n>` 或 `—` | … | … | `pending` |

`spec_ref` 列填该任务实现/验证的 spec 章节。如任务为基础设施搭建（如
`uv init`）或纯交付物（如评估报告），可填 `—`。多 spec 用逗号分隔。

每个任务必须在 `docs/task/active/task-*.json` 中存在同名条目。

## 4. 边界护栏

- 显式列出**不在本计划范围内**的事项，阻断范围漂移。

## 5. 完成标准

`green` 仅当：

- 第 3 节所有任务在对应任务文件中标记 `completed`
- 必要的评估证据已写入 `docs/eval-test/`
- 关联规格的成功标准已满足

关闭后，将本文件移至 `docs/exec-plan/archive/YYYY-Www/`。
