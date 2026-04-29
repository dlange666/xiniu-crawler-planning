# plan-20260429-codegen-red-eval

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-red-eval`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md` §3.1；`docs/codegen-pipeline.md` §4.6
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

让 codegen wrapper 对 red 结果负责留痕：即使 opencode 异常退出、漏写 eval，
或 wrapper gates 在 agent 自判之后变红，也必须在目标 worktree 的
`docs/eval-test/codegen-<host>-YYYYMMDD.md` 里记录最终 gate 结果、失败项和日志路径。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-501 | [scripts/codegen] red 结果强制写 eval-test 证据 | `codegen-output-contract.md` §3.1；`codegen-pipeline.md` §4.6 | `run_codegen_for_adapter.py` 在 gates 后创建或追加 wrapper eval；记录最终判定、gate 表、失败 gate、opencode exit code、log/worktree/branch | 单测覆盖缺失 eval 自动创建、已有 eval 追加 wrapper 结果；runner 单测、ruff、py_compile 通过 | `verifying` |

## 4. 边界护栏

- 不改变 opencode 产物允许写入范围；wrapper 只补充/追加 eval 证据。
- 不自动把 red 任务提交或开 PR；red worktree 仍留给人工 review。
- 不改变 crawl_task 状态语义；任一 gate fail 仍写 `failed/red`。
- 不调整 audit 阈值；`body_500_rate` profile 化另开任务处理。

## 5. 完成标准

`green` 仅当：

- T-20260429-501 在任务文件中标记 `completed`
- `run_codegen_for_adapter.py` red/green wrapper eval 行为有单元测试
- `uv run pytest tests/infra/test_codegen_task_runner.py -q` 通过
- `uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py` 通过
- `uv run python -m py_compile scripts/run_codegen_for_adapter.py` 通过
