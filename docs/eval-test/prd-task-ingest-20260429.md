# PRD 数据源任务入库验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-prd-task-ingest` / `T-20260429-201`
> **验证 spec**：`data-model.md` §4.1.1, §4.1.3；`domain-gov-policy.md` §2, §8
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本次验证回答：能否把 `docs/prd/policy-data-sources-phase1-20260427.md` 中
的第一阶段入口 URL 离线收录为本地 `crawl_task` 任务池，并保持重复运行幂等。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 无 PRD 入库脚本；WebUI 只能人工逐条创建任务 |
| Candidate（候选） | `scripts/ingest_prd_tasks.py` |
| 数据切片 | `docs/prd/policy-data-sources-phase1-20260427.md` 全量 URL |
| 评估口径 | URL 候选数、首次插入数、重复运行跳过数、data_kind 分布 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | `/tmp/prd-task-ingest.db` |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_prd_task_ingest.py -q

uv run ruff check scripts/ingest_prd_tasks.py tests/infra/test_prd_task_ingest.py

rm -f /tmp/prd-task-ingest.db /tmp/prd-task-ingest.db-wal /tmp/prd-task-ingest.db-shm
uv run python scripts/ingest_prd_tasks.py --db /tmp/prd-task-ingest.db
uv run python scripts/ingest_prd_tasks.py --db /tmp/prd-task-ingest.db

sqlite3 /tmp/prd-task-ingest.db \
  "SELECT data_kind, COUNT(*) FROM crawl_task GROUP BY data_kind ORDER BY data_kind;
   SELECT COUNT(*), COUNT(DISTINCT host) FROM crawl_task;"
```

## 4. 度量结果

| 指标 | 结果 |
|---|---:|
| PRD URL candidates | 156 |
| 首次 inserted | 156 |
| 首次 skipped_existing | 0 |
| 重复运行 inserted | 0 |
| 重复运行 skipped_existing | 156 |
| distinct host | 70 |

## 5. data_kind 分布

| data_kind | count |
|---|---:|
| announcement | 13 |
| news | 48 |
| planning | 1 |
| policy | 50 |
| policy_interpretation | 29 |
| regulation | 15 |

## 6. 本地 dev DB 结果

已对默认本地 DB 执行：

```bash
uv run python scripts/ingest_prd_tasks.py
uv run python scripts/ingest_prd_tasks.py
```

结果：

| DB | candidates | inserted | skipped_existing |
|---|---:|---:|---:|
| `runtime/db/dev.db` | 156 | 156 | 0 |
| `runtime/db/dev.db` repeat | 156 | 0 | 156 |

`runtime/db/dev.db` 是运行时产物，不加入 git。

## 7. 结论与决策

- **判定**：`green`
- **理由**：脚本离线解析 PRD 全量 URL 并成功写入 `crawl_task` /
  `crawl_task_execution`；重复运行不产生重复任务；单元测试与 ruff 通过。
- **风险**：`data_kind` 基于 PRD 行文本和标题启发式推断，后续 opencode/codegen
  逐站点执行时仍需按站点验证 adapter、seed、live smoke 与 audit。

## 8. 后续行动

| 事项 | 落点 |
|---|---|
| 逐站点 codegen 生成 adapter | 后续从 `crawl_task` 任务池按 host/data_kind 取任务 |
| 已有 adapter 直接采集 | NDRC / MOST 等已具备 adapter 的任务可由 runner 显式执行 |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：PRD 入口 URL 入库与幂等验证 green |
