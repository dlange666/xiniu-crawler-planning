# Plan: codegen autocommit

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-autocommit`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md`
- **状态**：`active`
- **负责角色**：`Planner / Generator / Evaluator`

## 2. 目标

让 `scripts/run_codegen_for_adapter.py` 在 wrapper gates 结束后自动提交并推送 codegen 分支：

- `green`：提交 plan/task/eval/adapter/seed/golden/test 完整交付物。
- `red`：只提交 eval 诊断报告，不提交半成品 adapter/test/golden。
- PR 创建和 merge 仍保留为人审动作。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-1001 | [codegen/wrapper] green 自动提交并推送交付分支 | `codegen-output-contract.md` §3.1 | 新增自动提交路径选择与 push；默认开启，可用 `--no-auto-commit` 关闭 | 单测覆盖 green 提交路径；ruff / pytest | `completed` |
| T-20260429-1002 | [codegen/wrapper] red 只提交 eval 诊断 | `codegen-output-contract.md` §3.1 | red 分支仅 stage eval，避免半成品 adapter 入史 | 单测覆盖 red 仅含 eval | `completed` |
| T-20260429-1003 | [docs/spec] 同步 pipeline 与 spec | `codegen-output-contract.md` §6 | 更新 `docs/codegen-pipeline.md` 与 spec rev 15 | 文档 diff review | `completed` |
| T-20260429-1004 | [eval] 验证 autocommit 行为 | `docs/eval-test/template.md` | 写入 `docs/eval-test/codegen-autocommit-20260429.md` | eval 判定 green | `verifying` |

## 4. 边界护栏

- 不自动创建 PR，不自动 merge。
- 不改变 codegen gate 阈值。
- 不提交 `.codegen-prompt.md`、`.codegen-feedback.md`、runtime DB/log/raw。
- red 不提交半成品 adapter/test/golden。

## 5. 完成标准

`green` 仅当：

- `scripts/run_codegen_for_adapter.py` 和相关测试通过 ruff
- 局部与全量 pytest 通过
- spec rev 与 pipeline 已同步
- 本计划对应 task/eval 证据齐全
