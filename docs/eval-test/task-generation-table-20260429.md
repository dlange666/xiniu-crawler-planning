# Eval · crawl_task_generation 表落地

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-task-generation-table` · `data-model.md` §4.1.2
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景

按 `data-model.md` §4.1.2 把 `crawl_task_generation` 表从 spec 落到 SQLite，把
"codegen 开发过程状态"从 `crawl_task_execution.status` 中分离。WebUI 同时暴露
`adapter_ready`（registry 派生）和 `generation_status`（DB 持久化）。

## 2. 复现命令

```bash
# 单元测试
uv run pytest tests/infra/test_task_generation_table.py -v

# Lint
uv run ruff check infra/storage/sqlite_store.py infra/codegen/ webui/ \
    scripts/ingest_prd_tasks.py scripts/run_codegen.py \
    tests/infra/test_task_generation_table.py

# 全套测试
uv run pytest tests/ -q

# 运行时验证（需 dev.db 已 seed）
uv run python scripts/run_webui.py &
sleep 2
curl -s http://127.0.0.1:8765/api/tasks?limit=5 | python3 -m json.tool | head -40
# 应看到每条 item 含 adapter_ready (bool) 与 generation_status (str)
```

## 3. Gate 结果

| Gate | Result |
|---|---|
| ruff (infra + webui + scripts + 新测试) | PASS |
| pytest tests/infra/test_task_generation_table.py | PASS（5 cases） |
| pytest tests/ 全量 | PASS（148） |
| 表结构存在性 | PASS（init_schema → SELECT * FROM crawl_task_generation 不报错） |
| 老 task backfill | PASS（init_schema 自动插 `pending`） |
| 状态转移 | PASS（pending → claimed → drafting → merged/failed） |
| 字段语义分离 | PASS（generation_status 与 execution.status 互不干扰） |

## 4. 设计要点

| 决策 | 理由 |
|---|---|
| 不在 `crawl_task` 加 `adapter_status` 字段 | 避免与 generation / execution / registry 形成四源数据，必然漂移。 |
| `adapter_ready` 仍由 registry 派生 | filesystem 是 ground truth；commit 了代码 = registry 立刻能看到。DB 字段会和代码漂移。 |
| 老 task 由 init_schema `INSERT OR IGNORE` 补 `pending` | 兼容已存在的 dev.db；不强制 migration。 |
| `mark_codegen_drafting` 只在 `claimed/drafting` 状态下生效 | 避免误把 `merged` 重置为 `drafting`（reattempt 必须先 re-claim）。 |
| `tier` / `pr_url` / `sandbox_run_id` 建表但不写 | M4 auto-merge-policy 落地时再用；现在写无意义。 |

## 5. 文件清单

- Schema: `infra/storage/sqlite_store.py`
- Wrapper: `infra/codegen/task_db.py`
- Entry: `scripts/run_codegen.py`
- WebUI store: `webui/stores/task_store.py`
- WebUI route: `webui/routes/tasks.py`
- WebUI frontend: `webui/frontend/src/main.tsx`
- ingest-prd: `scripts/ingest_prd_tasks.py`
- 测试: `tests/infra/test_task_generation_table.py`
- spec: `docs/prod-spec/data-model.md` §4.1.2、`docs/prod-spec/codegen-output-contract.md` rev 16
- plan/task: `docs/exec-plan/active/plan-20260429-task-generation-table.md`、`docs/task/active/task-task-generation-2026-04-29.json`

## 6. 已知 todo

- M4 auto-merge-policy 落地时再写 `tier` 与 `pr_url`。
- stale-heartbeat 回收 worker 暂未实现，索引 `idx_crawl_task_generation_stale_heartbeat` 已建。
- 当前 wrapper 的 `claim_codegen_task` 还从 `crawl_task_execution.status='scheduled'` 取候选；
  长期应改为从 `crawl_task_generation.status IN ('pending','failed')` 取，让"开发流"
  和"调度流"完全解耦。下个 plan 处理。

## 7. PR handoff

- title: `infra(codegen): persist crawl_task_generation lifecycle`
- body 要点：见 plan §1-§3
- notify-message 草稿：
  > codegen 开发状态现在从 task_execution 表分离到独立的 crawl_task_generation 表。
  > WebUI 列表加了 Adapter / Codegen / Status 三列，可同时看到代码合入、过程状态、爬取调度。
