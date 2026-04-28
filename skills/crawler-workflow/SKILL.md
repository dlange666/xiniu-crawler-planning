---
name: crawler-workflow
description: 在 xiniu-crawler 仓库或采用同一 AGENTS.md 控制面的仓库内启动任务时使用。本 skill 读取本地控制文档，判断任务属于执行、实验、清理、技术债哪条流，并路由到对应的 crawler-workflow 子 skill。
---

# Crawler Workflow

凡是采用 `xiniu-crawler` 控制面的仓库，每个任务都从本 skill 入口。

## 首读顺序

按以下顺序加载仓库本地控制文档：

1. `CLAUDE.md`
2. `AGENTS.md`
3. `AGENTS.md` 引用的任务相关文档

仓库本地文件是权威来源。本 skill 只是执行向导。

## 硬规则闸口

在路由或写任何代码之前，先把 `AGENTS.md` 的 Hard Rules 抽出来，逐条核对待
办任务是否违反。

硬规则是含绝对措辞的行（如 **禁止 / 不得 / 必须 / 不允许 / 一律不**）。

对每条与任务相关的硬规则：
1. 显式陈述该规则。
2. 确认拟采取的实现路径不违反它。
3. 若违反，立刻停下并告诉用户正确路径，再继续。

即使用户已经给出具体实现也不跳过本闸口。用户的意图是目标，实现路径仍必
须合规。

## 爬虫专属合规检查

本仓库属于爬虫平台。除通用 Hard Rules 外，每次进入实现前必须确认：

- 不会绕过验证码、登录认证、付费墙、技术 challenge、robots 明示拒绝
- 抓取层级遵循 `feed/sitemap → static → 接口拦截 → SSR/DOM → 渲染` 的递进顺序
- 原始页字节会被持久化、可回放
- 不在 source 层做去重；去重发生在解析层
- 不用 LLM 跑全量请求主路径；规则优先，AI 兜底

## Spec 编辑前置检查

凡 PR 触达 `docs/prod-spec/*.md`：

1. 判断是否"实质性改动"：影响实现 / 契约 / 默认值 / 接口 → 是
2. 是 → 同 PR 内：
   - 追加 `## 修订历史` 一行（rev / 日期 / 摘要 / PR 引用）
   - bump 顶部 frontmatter 的 `rev N` 与 `最近修订` 日期
   - breaking change 摘要前加 **[breaking]**
3. 否（仅排版/拼写/链接修复）→ 修订历史可不更，但说明理由记入 PR 描述

新建 spec 必须用 `docs/prod-spec/template.md` 起手；归档外部 PRD 用 `docs/prd/`；写工程研究用 `docs/research/`。

## 路由

写代码前，挑一条工作流：

- `crawler-workflow-execution`：主交付环路 `Spec -> Plan -> Task -> Code -> Evidence`
- `crawler-workflow-cleanup`：维护、过期代码清理、命名审计、迭代残留物清理
- `crawler-workflow-techdebt`：暂不入实现的非紧急跟踪事项

## 跨项目角色映射

如果在 `xiniu-crawler` 之外使用本 skill，不要只看角色名。先按以下顺序找本
地控制文档：

1. `AGENTS.md`
2. `WORKFLOW.md`
3. `CLAUDE.md`
4. `README.md`
5. `docs/architecture.md` 或同等控制文档

然后按"产物归属"而不是"标题文本"映射本地角色：

- `Planner`：拥有范围、规格、架构归属、执行计划输出
- `Generator`：拥有实现、代码改动、测试更新
- `Evaluator`：拥有验证、验收检查、评审结论、证据记录
- `Cleaner`：拥有维护、过期代码清理、命名审计、遗留整合

仓库若用 `designer / builder / reviewer / maintainer` 等别名，按产物归属映
射到上述四个工作流角色，而不是按标题字面。

## 仓库预期

- 上下文归属先于实现。
- 架构边界变更先更新文档。
- `docs/` 按生命周期分类（workflow / artifact / long-lived）；不要把每个子目录都套成 `active/completed/archive`。
- 业务代码留在 `domains/<context>/`。
- 共享技术能力留在 `infra/`。
- 专用 worktree 从主检出同步 `.env`，并复用主检出的 SQLite 根目录 `/Users/wangjisong/xiniu/code/xiniu-crawler/runtime/db/`（仅开发/测试场景；生产元数据走 PolarDB，原始页走阿里云 OSS）。
- 运行时产物不入 git。

## 快速判断

- 任务改产品行为、文档、代码、测试 → `crawler-workflow-execution`
- 任务是消除漂移、重复代码、过期分支、迭代残留 → `crawler-workflow-cleanup`
- 任务只需登记以备后查 → `crawler-workflow-techdebt`
