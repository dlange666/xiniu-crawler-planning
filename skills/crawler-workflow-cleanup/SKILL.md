---
name: crawler-workflow-cleanup
description: 清理 xiniu-crawler 代码库时使用。本 skill 应用 AGENTS.md 中的 Cleaner 工作流，包括死代码清理、命名审计，以及把遗留或迭代残留的过期实现合并到当前维护路径。
---

# Crawler Workflow · 清理流

适用于仓库整洁与维护类工作。

## 首读顺序

按顺序加载：

1. `CLAUDE.md`
2. `AGENTS.md`
3. 受影响的 domain 或 infra 路径

`AGENTS.md` 是清理范围与安全规则的权威。

跨仓库使用时，找拥有"维护、死代码清理、重构整洁、命名审计、遗留整合"产物
归属的角色，把它视作 Cleaner。

## 清理流程

1. 扫描临时脚本、死代码、重复逻辑、陈旧运行时产物、僵尸文件。
2. 审计命名与目录整洁度，尤其是已不再匹配真实职责的泛名。
3. 识别遗留分支、迭代残留物、活动代码中已被取代的路径。
4. 把幸存逻辑合并到当前维护实现；安全前提下删掉陈旧重复。
5. 对陈旧 `runtime/db/test_*.db` 快照：仅保留活跃使用的 + 最近 5 份保留快照；本周期清理更老的。
6. 若目录结构、命名或职责边界发生变化，同步文档。
7. 把清理动作记入 `docs/cleanup-log.md`。
8. 如果清理过程中发现非紧急的后续事项，推到 `docs/exec-plan/tech-debt-tracker.md`，不要悄悄扩大范围。

清理在专用 worktree 下执行时，env-backed 命令前先同步主检出的 `.env`；任何
DB 检查或临时 DB 工作仍指向主检出共享 DB 根
`/Users/wangjisong/xiniu/code/xiniu-crawler/runtime/db/`。

## 清理交付清单

每个改动仓库文件的清理任务，宣告完成前必须走完：

1. **分支**：先 `git checkout -b agent/cleanup-YYYYMMDD-<topic>` 再开始改文件。
2. **清理并提交**：所有改动在该分支上提交，不直接提交到 `main`。
3. **PR**：`gh pr create --title "cleanup(<scope>): <summary>" --body "..."`。
4. **清理日志**：动作记入 `docs/cleanup-log.md`。

> 邮件通知本期不接入；后续接入时再补充第 5 步。

## 硬规则

- `domains/archive/`（若存在）属于遗留归档，未获显式批准不得修改。
- 除非有当下且有合理依据的过渡计划，不要让新旧实现同时存活。
- 优先收敛到当前维护路径，不要在陈旧分支上叠加新一层包装。
- 未获显式确认前，不要把清理任务变成功能任务。
