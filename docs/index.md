# docs/ —— 控制面与文档索引

本目录是仓库的"控制面"，按生命周期分三类：**workflow / artifact / long-lived**。

## 顶层文件

| 文件 | 角色 |
|---|---|
| `architecture.md` | 仓库级 high-level 架构：分层、目录、依赖、Capability × Spec × Plan 对照表、关键决策 |
| `product-sense.md` | 产品方向、核心指标、不做什么 |
| `cleanup-log.md` | 工作流维度的清理动作记录（追加式） |

## 子目录

| 目录 | 类型 | 职责 | 索引 |
|---|---|---|---|
| `prod-spec/` | long-lived | 产品与基础设施规格（11 份 spec + 模板） | `prod-spec/index.md` |
| `prd/` | long-lived | 产品需求文档归档（产品/业务/合规方原稿） | `prd/index.md` |
| `research/` | long-lived | 工程视角研究底稿（调研、设计提案） | `research/index.md` |
| `exec-plan/` | workflow | 执行计划与路线图（active / archive；暂缓走 `deferred-plan.md`） | `exec-plan/index.md` |
| `task/` | workflow | 每个 PR 的任务状态文件（active / completed / archive） | 直接扫描 |
| `eval-test/` | artifact | 评估证据与回放工件 | `eval-test/template.md` |

## 命名约定（与 AGENTS.md `Doc Naming Conventions` 同源）

- **kebab-case**；新 Markdown 文件名优先描述性命名
- 若该目录有"前缀分组"（如 `prod-spec/{domain-,infra-,codegen-}*.md`、`exec-plan/{PLAN-,ROADMAP-}*.md`）→ 必须遵守
- 文档中需要长期演进的 spec 类文档：顶部带 frontmatter（`> **版本**：rev N · ...`），底部带 `## 修订历史`

## 入口顺序（新人 onboarding）

1. 顶层 `README.md`（项目背景）
2. `AGENTS.md`（仓库地图 + 硬规则）
3. `architecture.md`（架构）
4. `prod-spec/index.md`（规格速查）
5. `exec-plan/index.md`（当前在做什么）
