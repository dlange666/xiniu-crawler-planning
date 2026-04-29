# Default RPS 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-default-rps` / `T-20260429-601`
> **验证 spec**：`infra-fetch-policy.md` §2, §8；`data-model.md` §4.1.1
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本次验证回答：无明确站点限速时，系统默认是否按 `1.0 rps` 执行，同时保留
站点 seed / task 向下覆盖能力。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 默认 `politeness_rps=0.5` |
| Candidate（候选） | 默认 `politeness_rps=1.0` |
| 数据切片 | token bucket、seed loader、SQLite dev schema、WebUI 默认表单 |
| 评估口径 | 默认值一致性、向下覆盖守门、全量回归 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | pytest `tmp_path` |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_http.py tests/infra/test_seed_loader.py tests/infra/test_storage.py -q

uv run pytest tests/webui/test_webui_app.py -q

uv run ruff check infra/http/token_bucket.py infra/crawl/seed_loader.py infra/crawl/types.py infra/crawl/runner.py infra/storage/sqlite_store.py tests/infra/test_http.py tests/infra/test_seed_loader.py tests/infra/test_storage.py webui/routes/tasks.py webui/stores/task_store.py tests/webui/test_webui_app.py

uv run python -m py_compile infra/http/token_bucket.py infra/crawl/seed_loader.py infra/crawl/types.py infra/crawl/runner.py infra/storage/sqlite_store.py webui/routes/tasks.py webui/stores/task_store.py

uv run pytest tests/ -q

git diff --check
```

## 3.1 关联 PR

- Draft PR: https://github.com/dlange666/xiniu-crawler-planning/pull/12

## 4. 度量结果

| Gate | 结果 |
|---|---|
| infra 默认值单测 | `green`：24 passed |
| WebUI 默认值单测 | `green`：5 passed |
| ruff | `green`：All checks passed |
| py_compile | `green`：exit 0 |
| 全量测试 | `green`：89 passed |
| diff whitespace | `green`：无输出 |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| HostTokenBucket | 默认 `default_rps == 1.0` |
| host 覆盖 | host 配置高于默认时被 cap 到 1.0 |
| seed loader | seed 未写 `politeness_rps` 时默认 1.0 |
| SQLite schema | `crawl_task.politeness_rps` 默认 1.0 |

## 6. 结论与决策

- **判定**：`green`
- **理由**：默认值链路、向下覆盖守门、WebUI 表单与 SQLite DDL 均有测试或静态检查覆盖，全量回归通过。
- **风险**：默认值上调会让未显式配置低速的站点更快；robots、Retry-After、cooldown 与 warm-up 仍作为保护层。
- **阻塞项**：无。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 关闭哪些 task / plan | `T-20260429-601` completed；`plan-20260429-default-rps` archived |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：默认 politeness_rps 调整为 1.0 的验收记录 |
