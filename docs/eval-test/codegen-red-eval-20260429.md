# Codegen Red Eval Wrapper 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-red-eval` / `T-20260429-501`
> **验证 spec**：`codegen-output-contract.md` §3.1；`codegen-pipeline.md` §4.6
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本次验证回答：opencode 执行结果为 red 时，wrapper 是否能保证至少写出
`docs/eval-test/codegen-<host>-YYYYMMDD.md`，记录最终 gates 与失败原因。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 依赖 opencode 自行写 eval；wrapper 只打印 gates 到终端并更新 DB |
| Candidate（候选） | wrapper 在 gates 后调用 `record_wrapper_eval` 创建或追加 eval |
| 数据切片 | 单元测试临时 worktree |
| 评估口径 | 缺失 eval 自动创建；已有 eval 追加 wrapper gate 结果；命令 gate 通过 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | pytest `tmp_path` |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_codegen_task_runner.py -q

uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py

uv run python -m py_compile scripts/run_codegen_for_adapter.py

uv run pytest tests/ -q
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| codegen task runner 单测 | pass：6 passed |
| ruff | pass |
| py_compile | pass |
| 全量测试 | pass：87 passed |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| opencode/gates red 且 eval 缺失 | wrapper 创建 `docs/eval-test/codegen-<host>-YYYYMMDD.md`，判定为 `red` |
| opencode 已写 eval 但 wrapper gates red | wrapper 追加 `Wrapper Gate Result`，列出失败 gates 与日志路径 |

## 6. 结论与决策

- **判定**：`green`
- **理由**：wrapper 已能在 eval 缺失时创建 red 记录，在 eval 已存在时追加最终 gate 结果；局部测试、ruff、py_compile 与全量测试均通过。
- **风险**：wrapper 只保证证据存在，不自动修复 red 原因，也不自动提交 red worktree。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 调整 audit profile / `body_100_rate` | 后续质量门任务 |
| 关闭哪些 task / plan | 已关闭 `T-20260429-501` 与 `plan-20260429-codegen-red-eval` |
| PR | https://github.com/dlange666/xiniu-crawler-planning/pull/10 |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：记录 codegen wrapper red eval 兜底验收口径 |
