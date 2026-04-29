# Codegen Closure 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-closure` / `T-20260429-901`
> **验证 spec**：`codegen-output-contract.md` rev 12；`docs/codegen-pipeline.md` §4.5
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

NFRA retry 暴露出 agent 容易在单测通过后提前 red、误判旧 smoke DB checkpoint、
或把 JS shell/API 能力不足直接归因到 render/infra。本次把这些经验固化到
pipeline 和 wrapper per-task prompt。

## 2. 覆盖点

| 场景 | 防护 |
|---|---|
| 单测通过但 live smoke/audit 未跑 | prompt 和 pipeline 禁止写 green |
| 旧 `runtime/db/dev.db` 造成 0 records | live smoke 前强制 `rm -f runtime/db/dev.db*` |
| parser 单独可用但 runner 无数据 | red 前检查 seed URL、scope、robots、checkpoint、`ADAPTER_META.list_url_pattern` |
| JS shell 被误判 render | 必须先穷尽静态 JS、CDN JSON、XHR/fetch/API、feed/sitemap、SSR |
| worktree 外写入 | pipeline 明确禁止 `/tmp/*`、父目录、其它 worktree 和任意未授权绝对路径 |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_codegen_task_runner.py -q
uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py
uv run python -m py_compile scripts/run_codegen_for_adapter.py
uv run pytest tests/ -q
git diff --check
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| codegen task runner 单测 | `green`：13 passed |
| ruff | `green`：All checks passed |
| py_compile | `green`：exit 0 |
| 全量测试 | `green`：118 passed |
| diff whitespace | `green` |

## 5. 结论

- **判定**：`green`
- **理由**：agent prompt 与 pipeline 均包含完整收口协议；新增测试覆盖 per-task prompt 中的 smoke DB 清理、audit DB、red 前 parser/scope/checkpoint 排查。
- **风险**：prompt 只能提高 agent 自主收口概率，不能替代 wrapper gates；最终判定仍必须由 wrapper 复核。
