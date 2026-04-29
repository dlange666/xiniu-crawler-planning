# Render + Codegen Platform 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-render-codegen-platform` / `T-20260429-1201` / `T-20260429-1202` / `T-20260429-1203`
> **验证 spec**：`infra-render-pool.md` §3-§5, §7, §11；`infra-crawl-engine.md` §10；`codegen-output-contract.md` §3, §5-§6；`codegen-auto-merge.md` §2-§3
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

验证 headless render pool 与 codegen 平台 infra 化是否已交付可测试基础切片，
同时确认默认配置不会启动真实浏览器或绕过受保护页面。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 无 `infra/render`；codegen 能力主要集中在 wrapper 脚本 |
| Candidate（候选） | `infra/render` decision/pool + `infra/agent`/`sandbox`/`harness`/`codegen` 基础抽象 |
| 数据切片 | render decision、pool bytes gate、CrawlEngine renderer 注入、agent backend、tier1 path policy、command harness、compliance scanner、worker run-once |
| 评估口径 | 安全默认值、禁止矩阵、worker 成功/失败路径、全量回归 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | pytest `tmp_path` |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_render_pool.py tests/infra/test_crawl_render.py tests/infra/test_agent_backend.py tests/infra/test_sandbox.py tests/infra/test_harness.py tests/infra/test_codegen_worker.py -q

uv run ruff check infra/render infra/agent infra/sandbox infra/harness infra/codegen infra/crawl/runner.py infra/storage/sqlite_store.py infra/storage/protocols.py tests/infra/test_render_pool.py tests/infra/test_crawl_render.py tests/infra/test_agent_backend.py tests/infra/test_sandbox.py tests/infra/test_harness.py tests/infra/test_codegen_worker.py

uv run pytest -q

uv run ruff check .

git diff --check

uv run python -m json.tool docs/task/completed/task-render-codegen-platform-2026-04-29.json >/dev/null
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| targeted pytest | `green`：14 passed |
| targeted ruff | `green`：All checks passed |
| full pytest | `green`：160 passed |
| full ruff | `green`：All checks passed |
| diff whitespace | `green`：无输出 |
| task JSON parse | `green`：exit 0 |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| render disabled 默认值 | `RENDER_POOL_ENABLED=false` 时 render decision 返回 blocked |
| protected pages | captcha/challenge 文本即使 enabled 也不会渲染 |
| renderer pool | disabled failure、max bytes gate 均有单测 |
| crawler integration | adapter `should_render` 信号通过注入 renderer 解析 rendered HTML，并写 `fetch_record.rendered=1` |
| agent backend | Mock backend 记录请求；OpenCode backend 构造 `opencode run -m ... -f ...` |
| sandbox | tier-1 create host 只允许 adapter/seed/fixture/test/workflow/eval 路径，拒绝 `infra/` |
| harness | command gate 和合规 blocklist 均能返回结构化结果 |
| codegen worker | fake TaskSource + MockAgent + harness 覆盖 success、sandbox violation、harness failure |

## 6. 结论与决策

- **判定**：`green`
- **理由**：基础 render/codegen infra 模块均有单测；默认禁用与禁止矩阵生效；全量回归通过。
- **风险**：真实 Playwright 浏览器、render queue/backpressure、自动 PR、PR diff tier、canary/rollback 尚未实现，必须留在后续 workflow 原子任务。
- **阻塞项**：无。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 是否开新 task | 后续提升 `plan-20260428-render-pool-bootstrap` 的 Playwright/queue 任务；继续拆 `plan-20260428-codegen-bootstrap` 的 worker/auto-merge 任务 |
| 关闭哪些 task / plan | `T-20260429-1201`、`T-20260429-1202`、`T-20260429-1203` completed；`plan-20260429-render-codegen-platform` archived |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：render/codegen infra 基础切片验收记录 |
