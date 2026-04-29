# Codegen Task Runner 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-task-runner` / `T-20260429-301`
> **验证 spec**：`data-model.md` §4.1.1, §4.1.3；`codegen-output-contract.md` §3.1
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本次验证回答：`scripts/run_codegen_for_adapter.py` 能否从本地 `crawl_task`
任务表自动领取任务，并把领取、参数派生、完成状态更新这条链路固化为可测行为。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 只能通过 `--host` / `--entry-url` 手工传入 codegen 目标 |
| Candidate（候选） | `--from-task-db` 从 SQLite `crawl_task` / `crawl_task_execution` 自动 claim |
| 数据切片 | 单元测试临时 SQLite DB，构造多条 scheduled 任务 |
| 评估口径 | 领取优先级、指定 task_id、参数派生、completed/failed 状态更新 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | pytest `tmp_path` 自动生成 |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_codegen_task_runner.py -q

uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py

uv run python -m py_compile scripts/run_codegen_for_adapter.py

uv run python scripts/run_codegen_for_adapter.py --help

uv run pytest tests/ -q
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| task-runner 单测 | pass：4 passed |
| ruff | pass |
| py_compile | pass |
| CLI help | pass |
| 全量测试 | pass：85 passed |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| 自动领取下一条任务 | 只 claim `scheduled`，按 `priority ASC, created_at ASC, task_id ASC` 选择 |
| 指定 `--task-id` | 只 claim 指定且仍为 `scheduled` 的任务 |
| 参数派生 | `host`、`entry_url`、`business_context`、`data_kind`、`scope_mode`、`smoke_task_id` 从 DB 注入 |
| 状态收口 | 成功时写 `completed`、`last_run_status=green`、`run_count+1`、`consecutive_failures=0` |

## 6. 结论与决策

- **判定**：`green`
- **理由**：新的 DB 模式保持原手动参数模式不变，并把任务领取与状态更新变为可测试的本地 SQLite 行为。
- **风险**：本切片仍是单次执行器，不是常驻 worker；opencode 实际生成、live smoke 与 audit 仍由运行时环境决定，未在单元测试中调用外部站点。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 循环 worker / attempts 上限 / 后台调度 | 后续 `infra/codegen` worker 切片 |
| `crawl_task_generation` dev schema 落地 | 后续 codegen 平台正式 spec/DDL 切片 |
| 自动 PR 创建 | 后续在当前 handoff 基础上单独接入 |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：run_codegen_for_adapter.py 支持 crawl_task 自动 claim |
