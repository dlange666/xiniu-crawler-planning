# plan-20260429-codegen-task-runner

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-task-runner`
- **关联规格**：`docs/prod-spec/data-model.md` §4.1.1, §4.1.3；`docs/prod-spec/codegen-output-contract.md` §3.1
- **状态**：`completed`
- **负责角色**：`Planner`

## 2. 目标

让 `scripts/run_codegen_for_adapter.py` 支持从本地 `crawl_task` 表自动领取
`scheduled` 任务，派生 codegen 所需的 host、entry URL、scope 与业务上下文，
再复用现有 opencode + gates 流程完成单站点 adapter 生成。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-301 | [scripts/codegen] 从 crawl_task 自动 claim 并执行 | `data-model.md` §4.1.1, §4.1.3；`codegen-output-contract.md` §3.1 | `run_codegen_for_adapter.py` 新增 `--from-task-db` / `--task-db` / `--task-id`；SQLite `BEGIN IMMEDIATE` 原子领取 scheduled 任务并标记 running；gates 完成后标记 completed/failed；保留原手动参数模式 | 单元测试覆盖 claim、指定 task_id、参数派生、完成状态更新；ruff 与全量 pytest 通过；PR #8 | `completed` |

## 4. 边界护栏

- 不引入外部 Task API；本切片只支持本地 SQLite dev task 表。
- 不实现后台常驻 worker/loop；每次脚本执行只领取并处理一个任务，便于 cron 或人工重复调用。
- 不改变 opencode 调用与 gates 判定；仍由 `docs/codegen-pipeline.md` 约束 agent 产物。
- 不自动 merge PR；成功后仍输出人工 review/PR handoff 命令。

## 5. 完成标准

`green` 仅当：

- T-20260429-301 在任务文件中标记 `completed`
- `uv run pytest tests/infra/test_codegen_task_runner.py -q` 通过
- `uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py` 通过
- `uv run pytest tests/ -q` 通过
