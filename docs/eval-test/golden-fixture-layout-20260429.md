# Golden Fixture Layout 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-golden-fixture-layout` / `T-20260429-1101`
> **验证 spec**：`codegen-output-contract.md` §2-§5；`domain-gov-policy.md` §8；`codegen-auto-merge.md` §3；`infra-resilience.md` §4；`infra-crawl-engine.md` §11
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

验证 source golden HTML/JSON 是否已从 `domains/` 运行时代码目录迁移为
versioned test fixture，并确认 codegen wrapper 与 adapter pytest 复用同一套
golden 契约校验。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | golden fixture 与 adapter tests 分散在 `domains/gov_policy/<source>/` 和 `tests/gov_policy/` |
| Candidate（候选） | golden fixture 位于 `tests/domains/gov_policy/<source>/fixtures/`，adapter tests 位于 `tests/domains/gov_policy/<source>/test_adapter.py` |
| 数据切片 | CSRC、MOST、NDRC、NFRA、SASAC adapter fixtures；codegen wrapper path helpers；golden contract helper |
| 评估口径 | 目录归属、golden 配对/覆盖校验复用、codegen gate、source adapter 回归、全量回归 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | 无 |

## 3. 复现命令

```bash
uv run pytest tests/domains/gov_policy tests/infra/test_codegen_task_runner.py tests/infra/test_adapter_contract.py -q

uv run ruff check scripts/run_codegen_for_adapter.py infra/adapter_contract tests/domains/gov_policy tests/infra/test_codegen_task_runner.py tests/infra/test_adapter_contract.py tests/conftest.py

uv run pytest -q

uv run ruff check .

git diff --check

uv run python -m json.tool docs/task/completed/task-golden-fixture-layout-2026-04-29.json >/dev/null
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| targeted pytest | `green`：55 passed |
| targeted ruff | `green`：All checks passed |
| full pytest | `green`：146 passed |
| full ruff | `green`：All checks passed |
| diff whitespace | `green`：无输出 |
| task JSON parse | `green`：exit 0 |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| golden fixture 归属 | `domains/gov_policy/<source>/` 下不再保留 `*golden*` 文件 |
| tests 镜像目录 | 每个 source 均有 `tests/domains/gov_policy/<source>/test_adapter.py` 与 `fixtures/` |
| contract helper | `infra/adapter_contract/golden.py` 统一校验 fixture 存在、HTML/JSON 配对、list/detail 覆盖 |
| fixture contract 回归 | `tests/infra/test_adapter_contract.py` 扫描所有 gov_policy source fixtures，防止聚合 JSON 或缺配对文件回流 |
| codegen wrapper | golden gate、prompt、commit path 均指向 `tests/domains/<context>/<source>/fixtures/` |
| active specs | 关联 spec 已更新路径契约并 bump revision |

## 6. 结论与决策

- **判定**：`green`
- **理由**：目录迁移、共享契约 helper、codegen wrapper 路径、source adapter 单测、全量 pytest、ruff 与 diff check 均通过。
- **风险**：历史 research 或旧 eval 文档可能仍包含旧路径示例；执行时以 active spec 与当前 codegen wrapper 为准。
- **阻塞项**：无。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 关闭哪些 task / plan | `T-20260429-1101` completed；`plan-20260429-golden-fixture-layout` archived |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：golden fixture tests 镜像目录迁移与 contract helper 复用验收记录 |
