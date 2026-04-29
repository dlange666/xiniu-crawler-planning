# plan-20260430-intro-sync

## 1. 元信息

- **Plan ID**：`plan-20260430-intro-sync`
- **关联规格**：`docs/prod-spec/index.md`（spec 数量）；`docs/prod-spec/infra-render-pool.md`（render 状态变更）
- **状态**：`completed`
- **负责角色**：`Planner`
- **关联 PR**：https://github.com/dlange666/xiniu-crawler-planning/pull/26（commit f67bd23）

## 2. 目标

把 `intro/xiniu-crawler-introduction.html` 的内容与 README 的 spec 数量同步到 2026-04-30 的真实仓库状态。当前 intro 在以下点位与实现脱节：spec 数量、目录结构 ASCII、`infra/` 子模块清单、`domains/gov_policy/` 结构、能力模块表中的 render 状态、里程碑表中的 M1/M3.5 进展、国务院部委名单与已落地 adapter 不一致。

PDF 版本（`xiniu-crawler-introduction.pdf`）暂不在本计划范围内重新生成；HTML 是事实源，PDF 留给人工流程后续刷新。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260430-101 | [intro] 同步项目介绍 HTML 与 README spec 数量 | `prod-spec/index.md` | 更新 §4 能力模块表 render 状态；§5 部委名单；§7 仓库结构 ASCII（spec 数量、`infra/` 子模块、`domains/gov_policy/` 结构、`task/` 子目录）；§8 里程碑（M1 已完成、M2 部分落地、M3.5 包含 render）；同步 `README.md` "10 份 spec" → 11 份 | 人工 diff 比对 intro html 与当前仓库目录树；`ls docs/prod-spec/`、`ls infra/`、`ls domains/gov_policy/` 与 ASCII 一致 | `pending` |

## 4. 边界护栏

- 不重新生成 PDF（PDF 由人工浏览器打印流程刷新）。
- 不修改 intro 的视觉样式与图表（SVG）。
- 不动业务规格内容（采集对象 / 36 字段 / 合规底线）；只改与目录、状态、计数有关的句子。
- 不批量重写 README 的其他段落；只改 spec 数量这一项。

## 5. 完成标准

`green` 仅当：

- T-20260430-101 标记 `completed`
- intro html 中 spec 数量、目录结构、能力表 render 状态、里程碑均与当前仓库一致
- README.md "10 份 spec" 已修正
- 不引入新文件（除本计划与对应 task 文件外）
