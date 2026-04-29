# Codegen Autocommit Evaluation

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-autocommit` / `T-20260429-1001` / `T-20260429-1002` / `T-20260429-1003` / `T-20260429-1004`
> **验证 spec**：`codegen-output-contract.md` §3.1
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本评估验证 codegen wrapper 是否能在 gates 完成后自动提交并推送结果分支：green 提交完整 codegen 交付物，red 只提交 eval 诊断报告。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | wrapper 只输出手工 commit/push 命令 |
| Candidate（候选） | wrapper 默认 `--auto-commit`：green 提交完整产物；red 只提交 eval |
| 数据切片 | `scripts/run_codegen_for_adapter.py` 单元测试与全量测试 |
| 评估口径 | JSON 校验、py_compile、ruff、局部 pytest、全量 pytest |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | 无；本次未新增运行时 DB 工件 |

## 3. 度量结果 · 聚合

复现命令：

```bash
uv run python -m json.tool docs/task/active/task-codegen-autocommit-2026-04-29.json >/dev/null
uv run python -m py_compile scripts/run_codegen_for_adapter.py
uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py
uv run pytest tests/infra/test_codegen_task_runner.py -q
uv run pytest tests/ -q
```

结果：

```text
ruff: All checks passed
pytest tests/infra/test_codegen_task_runner.py -q: 18 passed
pytest tests/ -q: 145 passed
```

## 4. 度量结果 · 按切片

| 切片 | 结果 | 说明 |
|---|---|---|
| green commit path | PASS | 单测覆盖 plan/task/eval/source/test 被纳入提交，`.codegen-prompt.md` 被排除 |
| red commit path | PASS | 单测覆盖 red 仅提交 eval |
| CLI 兼容性 | PASS | `--auto-commit` 默认开启，可用 `--no-auto-commit` 关闭 |
| spec/pipeline | PASS | `codegen-output-contract.md` rev 15 与 `docs/codegen-pipeline.md` 已同步 |

## 5. 异常案例

| 案例 | 处理 |
|---|---|
| green gates 通过但 commit/push 失败 | runner 退出码为 1；DB 不标 completed |
| red gates 失败且产生半成品 adapter | 只提交 eval report，不提交 adapter/test/golden |
| 调试时不希望自动提交 | 使用 `--no-auto-commit` |

## 6. 结论与决策

- **判定**：`green`
- **理由**：代码、测试、spec、pipeline 均已同步，局部与全量验证通过。
- **风险**：green 自动提交后仍需要人审开 PR/merge，避免自动合并不合格实现。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 开 PR | `agent/infra-20260429-codegen-autocommit` |
| PR 链接 | https://github.com/dlange666/xiniu-crawler-planning/pull/22 |
| 后续实测 | 下一个 source codegen 观察 green/red 分支提交行为 |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：codegen autocommit 验收 green |
