# Domain Source Layout 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-domain-source-layout` / `T-20260429-801`
> **验证 spec**：`codegen-output-contract.md` §2；`domain-gov-policy.md` §8
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

验证旧的横向 `adapters/`、`seeds/`、`golden/` 目录是否已迁移为
`domains/<context>/<source>/` source 聚合目录，并确保 codegen 后续只产出新
路径。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | NDRC 分散在 `domains/gov_policy/adapters/`、`seeds/`、`golden/` |
| Candidate（候选） | NDRC 聚合到 `domains/gov_policy/ndrc/` |
| 数据切片 | NDRC 手写 adapter + codegen wrapper 路径 helper + adapter registry |
| 评估口径 | 目录迁移、registry discover、codegen artifact path、NDRC golden 单测、全量回归 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | 无 |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_adapter_registry.py tests/infra/test_codegen_task_runner.py tests/gov_policy/test_ndrc_adapter.py -q

uv run ruff check infra/adapter_registry/registry.py infra/adapter_registry/meta.py scripts/run_codegen_for_adapter.py scripts/run_crawl_task.py tests/infra/test_adapter_registry.py tests/infra/test_codegen_task_runner.py tests/gov_policy/test_ndrc_adapter.py

uv run python -m py_compile infra/adapter_registry/registry.py infra/adapter_registry/meta.py scripts/run_codegen_for_adapter.py scripts/run_crawl_task.py

uv run pytest tests/ -q

git diff --check
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| targeted pytest | `green`：37 passed |
| ruff | `green`：All checks passed |
| py_compile | `green`：exit 0 |
| full pytest | `green`：95 passed |
| diff whitespace | `green`：无输出 |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| NDRC source 目录 | adapter、seed、golden HTML 均位于 `domains/gov_policy/ndrc/` |
| registry | 默认扫描 `domains/<context>/<source>/<source>_adapter.py`，迁移期兼容旧 adapters 目录 |
| codegen wrapper | artifact helper 与 prompt 均指向 source 聚合目录 |
| active spec | `codegen-output-contract.md` 与 `domain-gov-policy.md` 使用新路径契约 |

## 6. 结论与决策

- **判定**：`green`
- **理由**：source 聚合目录迁移、registry 发现、codegen 路径 helper、NDRC golden 单测和全量回归均通过。
- **风险**：历史 research 原稿仍可能包含旧路径示例；执行时以 active spec 为准。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 关闭哪些 task / plan | `T-20260429-801` completed；`plan-20260429-domain-source-layout` archived |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：source 聚合目录迁移验收记录 |
