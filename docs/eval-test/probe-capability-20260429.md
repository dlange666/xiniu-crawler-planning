# Source Probe Capability 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-probe-capability` / `T-20260429-401`
> **验证 spec**：`infra-crawl-engine.md` §6.3；`codegen-output-contract.md` §3.1；`infra-render-pool.md` §1
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本次验证回答：codegen agent 能否在写 adapter 前，通过受控 infra 探查入口站点，
识别 static HTML、JSON API 与需要未来 render-pool 的 SPA shell，并留下可回放证据。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | codegen agent 直接用自身抓取能力判断页面类型，JS SPA 和 JSON API 发现不可控 |
| Candidate（候选） | `infra/source_probe` + `scripts/probe_source.py --mode auto` 统一执行 robots gate、fetch、JSON 候选发现、SPA shell 判定与 artifact 留存 |
| 数据切片 | 单元测试构造响应；live probe 覆盖 `www.gov.cn/yaowen/` 与 `flk.npc.gov.cn/index` |
| 评估口径 | verdict 正确性、robots gate、artifact 写入、CLI 可用性、全量回归 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | 无；本评估仅使用 `runtime/probe/` 运行时 artifact |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_source_probe.py -q

uv run ruff check infra/source_probe scripts/probe_source.py tests/infra/test_source_probe.py

uv run python -m py_compile scripts/probe_source.py infra/source_probe/probe.py

uv run python scripts/probe_source.py --help

uv run python scripts/probe_source.py \
  --url https://www.gov.cn/yaowen/ \
  --host www.gov.cn \
  --mode auto \
  --out runtime/probe/www_gov_cn_test

uv run python scripts/probe_source.py \
  --url https://flk.npc.gov.cn/index \
  --host flk.npc.gov.cn \
  --mode auto \
  --out runtime/probe/flk_test

uv run pytest tests/ -q
```

## 4. 度量结果

| Gate | 结果 |
|---|---|
| source-probe 单测 | pass：4 passed |
| ruff | pass |
| py_compile | pass |
| CLI help | pass |
| `www.gov.cn/yaowen/` live probe | pass：verdict=`json_api`，推荐 `https://www.gov.cn/yaowen/liebiao/YAOWENLIEBIAO.json` |
| `flk.npc.gov.cn/index` live probe | pass：verdict=`headless_required`，signals 包含 `js_shell_detected` |
| 全量测试 | pass：89 passed |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| HTML 内 JSON 候选 | 写入 `entry.html`、`json-candidate-1.json`、`probe-result.json`，verdict=`json_api` |
| JS redirect | 先写入口响应，再跟随同站重定向，保留 `redirected.html` |
| SPA shell | 低可见文本 + bundle/root 信号时返回 `headless_required` |
| robots disallow | robots gate 拒绝时不调用 fetch，verdict=`robots_disallow` |
| live JSON API | 国务院要闻入口能发现真实 JSON 列表接口 |
| live SPA | 国家法律法规数据库入口不尝试绕过，明确标记需要 render-pool |

## 6. 结论与决策

- **判定**：`green`
- **理由**：受控探查能力覆盖 robots gate、静态入口、JSON API 发现、JS redirect 与 SPA shell 判定；单测、CLI、ruff、py_compile 与全量回归均通过。
- **风险**：headless 浏览器池尚未实现，`headless_required` 站点仍会在 codegen 阶段红灯退出。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| render-pool M5 实现 | 后续 `infra/render_pool` 切片 |
| 将 probe 自动串入 codegen runner | 后续 `scripts/run_codegen_for_adapter.py` 切片 |
| 关闭哪些 task / plan | 已关闭 `T-20260429-401` 与 `plan-20260429-probe-capability` |
| PR | https://github.com/dlange666/xiniu-crawler-planning/pull/9 |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：记录 source probe 能力验收口径与 live probe 证据 |
