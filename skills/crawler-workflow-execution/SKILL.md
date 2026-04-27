---
name: crawler-workflow-execution
description: 当任务属于 xiniu-crawler 仓库主交付环路时使用。本 skill 应用 AGENTS.md 中的 Planner/Generator/Evaluator 工作流，并使所有变更与"文档先行"的交付节奏对齐。
---

# Crawler Workflow · 主交付环路

适用于走完整交付环路的工作：

`Spec -> Plan -> Task -> Code -> Evidence`

## 首读顺序

按顺序加载：

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/prod-spec/`、`docs/exec-plan/`、`docs/eval-test/` 下相关文件，以及受影响的 domain 路径

## 选择当前角色

修改前先选定当前角色：

- `Planner`：做上下文归属，保持 `docs/prod-spec/` 最新，边界变更先更新 `docs/architecture.md`，把已批准的工作写入 `docs/exec-plan/active/`
- `Generator`：实现一个已批准的原子任务，更新触达的代码、测试、相关文档，并推进 `docs/task/` 下对应文件中的任务状态
- `Evaluator`：独立验证（对照规格与计划），为 `red` 与 `green` 都写下 `docs/eval-test/` 记录，更新对应任务文件；只有计划下所有任务完成后才关闭计划

如果目标仓库角色名不同，按"产物归属"映射：

- 规格 / 架构 / 计划 / 任务拆解 → `Planner`
- 代码 / 测试 / 实现 → `Generator`
- 评审 / 验证 / 验收 / 证据 → `Evaluator`

## 执行规则

- 业务逻辑放在 `domains/` 下正确的 bounded context。
- 不跨 domain 触达对方私有内部。
- 共享技术能力放 `infra/`，不放业务模块。
- 架构边界变更先更新文档，再改代码。
- 若任务涉及运行时数据或 schema：开发/测试用 `runtime/db/` 下的 SQLite；生产元数据走 PolarDB；schema 变更走 drop-and-recreate，不写 `ALTER TABLE` 回填脚本。
- 若任务在专用 worktree 下执行，env-backed 命令前先从主检出同步 `.env`，本地 DB 路径仍指向主检出的 `/Users/wangjisong/xiniu/code/xiniu-crawler/runtime/db/`。

## 输出纪律

- `docs/` 只放文档。
- 严格遵循 `AGENTS.md` 的 docs 分类：workflow / artifact / long-lived 各自有不同目录形态。
- 运行时日志、CSV、生成的报告、本地数据库都不进 `docs/`。
- 运行时产物不入 git。

## 完成标准

不要停在"代码改完"就收尾，按当前角色走完环路：

- `Planner`：spec 和 plan 清晰到可被原子执行
- `Generator`：实现、测试、任务状态都已更新
- `Evaluator`：证据已写入，任务/计划状态反映结果

## Generator 交付清单

每个改动仓库文件的 Generator 任务，宣告完成前必须走完以下步骤：

1. **分支**：先 `git checkout -b agent/<type>-YYYYMMDD-<topic>` 再开始改文件。type ∈ `feature | cleanup | fix | docs | infra | spike`。
2. **实现**：在正确的 bounded context 下更新代码、测试、相关文档。
3. **提交**：在该分支上至少一次提交，禁止直接提交到 `main`。
4. **PR**：`gh pr create --title "<type>(<scope>): <summary>" --body "..."`。标题格式见 `AGENTS.md`。
5. **任务状态**：在 `docs/task/` 下对应文件中更新该任务，工作线关闭则把文件移出 `docs/task/active/`。

> 邮件通知本期不接入；后续接入时再补充第 6 步（参考 `docs/exec-plan/tech-debt-tracker.md` 中的 TD-002）。

任务文件中标 `completed` 的前置条件是：PR 已创建。
