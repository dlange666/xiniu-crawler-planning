# plan-20260429-prd-task-ingest

## 1. 元信息

- **Plan ID**：`plan-20260429-prd-task-ingest`
- **关联规格**：`docs/prod-spec/data-model.md` §4.1.1, §4.1.3；`docs/prod-spec/domain-gov-policy.md` §2, §8
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

把 `docs/prd/policy-data-sources-phase1-20260427.md` 中的第一阶段数据源入口
收录为本地 dev SQLite 中的 `crawl_task` 与 `crawl_task_execution` 记录，为
后续 opencode/codegen 逐站点生成 adapter 与实际采集提供任务池。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-201 | [scripts] PRD 数据源收录到 crawl_task | `data-model.md` §4.1.1, §4.1.3；`domain-gov-policy.md` §2, §8 | 新增 `scripts/ingest_prd_tasks.py`：解析 PRD 中 URL，推断 host/data_kind/scope，幂等写入 `crawl_task` 与 `crawl_task_execution`；默认只触达本地 SQLite，不联网 | 单元测试覆盖 URL 清洗、data_kind 推断、幂等入库；在临时 DB 上 dry-run 与实际 insert 可复现 | `verifying` |

## 4. 边界护栏

- 不启动真实抓取；不访问 PRD 中的任何目标站点。
- 不生成或修改 adapter；opencode/codegen 后续基于已入库任务逐站点执行。
- 不修改 `docs/prod-spec/data-model.md` DDL；本任务只使用既有 `crawl_task` 子集。
- 不写生产数据库；默认写 `runtime/db/dev.db` 或显式传入的 SQLite 路径。

## 5. 完成标准

`green` 仅当：

- T-20260429-201 在对应任务文件中标记 `completed`
- `uv run pytest tests/infra/test_prd_task_ingest.py -q` 通过
- `uv run ruff check scripts/ingest_prd_tasks.py tests/infra/test_prd_task_ingest.py` 通过
- 使用临时 DB 执行 PRD 入库脚本，能输出 inserted/skipped 统计且重复运行不新增重复任务
