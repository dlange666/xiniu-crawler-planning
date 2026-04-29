# Plan · crawl_task_generation 表落地 + WebUI 暴露 codegen 状态

> **类型**：`infra-plan`
> **关联 spec**：`docs/prod-spec/data-model.md` §4.1.2
> **日期**：2026-04-29
> **PR 名**：infra(codegen): persist crawl_task_generation lifecycle

## 1. 背景

spec `data-model.md` §4.1.2 早已定义 `crawl_task_generation` 表（codegen 过程状态：
pending / claimed / drafting / sandbox_test / pr_open / merged / failed），
但 `infra/storage/sqlite_store.py` 一直没建。结果：

- codegen wrapper 把"开发完成"硬塞进 `crawl_task_execution.status='completed'`，
  和"爬取完成"语义混淆。
- 直接走 `--host` 参数（不走 `--from-task-db`）跑的 codegen，没有任何 task 行被
  更新，无法区分"开发过 vs 没开发过"。
- WebUI 想展示"哪些 task 的 adapter 已开发"只能从 `infra/adapter_registry`
  filesystem 派生，无法看到过程状态（claimed / drafting / pr_open / failed）。

## 2. 目标

让"adapter 开发完成度"在三个层级各有权威源：

| 层级 | 权威源 | 含义 |
|---|---|---|
| 文件级 | `infra/adapter_registry`（filesystem） | adapter 代码是否合入了仓库 |
| 过程级 | `crawl_task_generation.status` | 这条 task 的 codegen 流程走到哪一步 |
| 执行级 | `crawl_task_execution.status` | 爬取/canary 调度状态 |

WebUI 三者并列展示。

## 3. 原子任务

| 任务 ID | 内容 | 关联 spec | DoD |
|---|---|---|---|
| T-20260429-1101 | [infra/storage] 建 `crawl_task_generation` 表 | `data-model.md` §4.1.2 | `init_schema()` 后 SELECT 不报错；新建 task 自动插入 `pending` 行 |
| T-20260429-1102 | [infra/codegen] wrapper 写入 generation 生命周期 | `codegen-output-contract.md` §3.1 | claim → `claimed`，agent 调用前 → `drafting`，gates 完成 → `merged`/`failed` |
| T-20260429-1103 | [webui] /api/tasks 暴露 generation_status + adapter_ready | — | 响应中包含两个字段；adapter_ready 来自 registry，generation_status 来自 DB |
| T-20260429-1104 | [webui/frontend] 任务列表加 Adapter 列、Codegen 列、操作列 | — | 列表显示三层状态 + 详情按钮；汇总条显示 X/Y |
| T-20260429-1105 | [docs] 更新 data-model §4.1.2 标注"已实施"；更新 codegen-output-contract changelog | — | spec 与代码状态一致 |

## 4. 护栏

- 不在 `crawl_task` 表上加新字段——避免和 generation/execution/registry 形成四源数据。
- generation 行**懒插入**：在 task 创建时插入 `pending`，老 task 跑 init_schema
  时 backfill `INSERT OR IGNORE`。
- adapter_ready 仍然由 registry 派生（filesystem ground truth），不依赖 DB
  字段——避免 commit 了代码但 DB 没更新导致漂移。
- 不动 `crawl_task_execution.status` 的语义；codegen 完成时 generation→merged，
  execution 仍走原有 `completed` 流程（爬取 smoke 通过才设）。

## 5. Gates

- `uv run ruff check infra/storage/sqlite_store.py infra/codegen/ webui/`
- `uv run pytest tests/ -q`
- 新增 `tests/infra/test_task_generation_table.py` 覆盖：建表、状态转移、并发 claim
- 手动验证：`scripts/run_webui.py` 起服务，`/ui/tasks` 列表显示三列状态

## 6. 不做的

- `crawl_task_generation` 的 `tier` / `pr_url` / `sandbox_run_id` 字段先建表但
  wrapper 不写（M4 auto-merge-policy 落地时再接）。
- 不实现 stale-heartbeat 回收（spec §4.1.2 提到的 `idx_stale_heartbeat`）。
- `dispatch` 与 `recovery` worker 是后续 plan，本期只让 wrapper 写状态。
