# plan-20260429-default-rps

## 1. 元信息

- **Plan ID**：`plan-20260429-default-rps`
- **关联规格**：`docs/prod-spec/infra-fetch-policy.md` §2, §8；`docs/prod-spec/data-model.md` §4.1.1
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

把无明确站点限速时的默认 host 礼貌性速率调整为 `1.0 rps`。已有站点或任务
显式配置的更低 `politeness_rps` 继续生效，不从 robots 推断速率。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-601 | [infra/fetch] 默认 politeness_rps 调整为 1.0 | `infra-fetch-policy.md` §2, §8；`data-model.md` §4.1.1 | 更新 `HostTokenBucket`、seed/task 类型默认值、seed loader、CrawlEngine、SQLite DDL、WebUI 表单与文档默认值；站点 seed 仅更新注释 | 单测覆盖 token bucket 默认值、seed loader 默认值、SQLite 默认值；ruff、py_compile、全量 pytest | `verifying` |

## 4. 边界护栏

- 不改变 robots / Retry-After / cooldown 行为。
- 不把已有明确低速站点提升到 1.0；NDRC 仍保持 `politeness_rps: 0.3`。
- 业务域 seed/task 仍只能向下覆盖默认值。
- 不实现自动学习 RPS；只调整静态默认值。

## 5. 完成标准

`green` 仅当：

- T-20260429-601 在任务文件中标记 `completed`
- 关联 spec 已 bump rev 并写修订历史
- `uv run pytest tests/infra/test_http.py tests/infra/test_seed_loader.py tests/infra/test_storage.py -q` 通过
- `uv run ruff check infra/http/token_bucket.py infra/crawl/seed_loader.py infra/crawl/types.py infra/crawl/runner.py infra/storage/sqlite_store.py tests/infra/test_http.py tests/infra/test_seed_loader.py tests/infra/test_storage.py` 通过
- `uv run pytest tests/ -q` 通过
