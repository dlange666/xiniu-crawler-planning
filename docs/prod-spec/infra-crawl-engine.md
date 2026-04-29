# Infra 通用爬虫引擎

> **版本**：rev 6 · **最近修订**：2026-04-29 · **状态**：active
> **实施状态**：MVP 已实现核心（commit 1987ac8）；高级特性（host_score 外层 / aging / AI relevance）随阶段演进。

> 适用：`infra/crawl/` 模块。本 spec 规定通用爬虫引擎的对外契约——
> business-agnostic、由 adapter resolver 注入业务，按 TaskSpec 参数化调度策略。
>
> 与 `codegen-output-contract.md` 互补：那个 spec 管"adapter 长什么样"，
> 本 spec 管"引擎怎么调度 adapter"。

## 1. 模块构成

```
infra/crawl/
├── runner.py                    CrawlEngine（主类）+ RunReport
├── types.py                     TaskSpec / SeedSpec / Parse* / Attachment / SourceMetadata
├── strategies.py                BFS / DFS 优先级公式
├── scope.py                     4 种 scope mode 闸口
├── seed_loader.py               YAML → SeedSpec
├── dedup.py                     联合键去重（business-agnostic）
└── pagination_helpers.py        通用翻页发现工具

infra/source_probe/
├── probe.py                     受控 source probe：static / JSON API / headless_required
└── __init__.py

scripts/probe_source.py          codegen 调用的受控探查 CLI
```

## 2. 入口契约

```python
class CrawlEngine:
    def __init__(
        self, *,
        task: TaskSpec,                          # 任务参数（strategy/scope/max_depth）
        seed: SeedSpec,                          # 单 host 入口配置
        adapter_resolver: Callable[[str], Any],  # host → adapter module（业务侧注入）
        run_id: str | None = None,
    ): ...
    
    def run(self) -> RunReport: ...
    def close(self) -> None: ...
```

**依赖规则**：

- `infra/crawl/` 不 import `domains/*`（架构 §3）
- adapter resolver 由调用方（通常是 scripts/ 或 codegen worker）注入
- adapter 模块必须暴露：`ADAPTER_META` 字典 + `parse_list(html, url)` + `parse_detail(html, url)`（详见 codegen-output-contract.md §2）

## 3. Routing Order（调度顺序）

> 实现 research §3-§4 推荐的"层内近似 BFS + 全局优先级堆"。

### 3.1 两级调度（host → URL）

| 层级 | 维度 | 当前实现 |
|---|---|---|
| 外层（选 host） | host_score = `task_priority + aging_bonus + fairness_debt + host_health - cooldown_penalty` | 单 host 场景退化为 round-robin；`HostTokenBucket` 已实现 cooldown_penalty。多 host 场景的 host_score 待 M3.5 codegen 启用后做（TD-018） |
| 内层（选 URL） | priority_score（见 §3.2） | 已实现 |

### 3.2 内层 priority_score 公式（演进路线）

| 阶段 | 公式 | 实施状态 |
|---|---|---|
| **rev 1（当前）** | `priority = depth_weight(depth, strategy) + base_score`<br>BFS: `(max_depth + 1 - depth) * 100 + base`<br>DFS: `depth * 100 + base` | ✅ infra/crawl/strategies.py |
| rev 2 | + `anchor_quality`（adapter 报告 anchor text 质量） | 待 codegen 接入后 |
| rev 3 | + `parent_quality`（父页面解析成功度） | 同上 |
| rev 4 | + `aging_bonus`（防饥饿；frontier 在出队时计算） | 多 host 场景启用 |
| rev 5 | + `relevance`（AI 相关性打分） | M3 AI 抽取启用后 |
| rev 6 | + `freshness`（URL 含日期 + last_modified） / `host_budget_bonus` / `trap_risk` | 完整 7 因子，对应 research §3 |

### 3.3 BFS 行为示例（NDRC 实测）

| 时间 | 操作 | Frontier 状态 |
|---|---|---|
| T+0 | 入 seed list_0（depth=0, p=200.7） | [list_0] |
| T+0 | 出 list_0 → 抓 + parse_list | — |
| T+2s | 入 list_1..8（各 p=200.7）+ detail_0..24（各 p=100.5） | [list_1..8, detail_0..24] |
| T+4s | 出 list_1（p 最高） | [list_2..8, detail_0..49] |
| ... | 9 个 list 翻完 | [detail_0..224] |
| T+~20s | 开始抓 detail_0 | — |
| ... | detail_0 解析 → 入 interpret_0 (p=0.4)、attach_0 (p=0.3)（depth=2 但 p 远低于 depth=1） | — |
| T+~470s | 225 detail 抓完 | [interpret_0..224, attach_0..N] |
| T+~700s+ | 抓 interpret + attachments | — |

**结论**：纯 BFS 严格按 depth 0 → 1 → 2 顺序。预算耗尽时优先级浅者先收齐。

## 4. Scope（作用域闸口）

`scope_allows(candidate_url, parent_url, mode, ...)` 4 种 mode：

| mode | 通过条件 | 适用 |
|---|---|---|
| `same_origin` | (scheme, host, port) 完全相同 | 默认；最严 |
| `same_etld_plus_one` | eTLD+1 相同（MVP 简化为最后两段） | 同集团多子站 |
| `url_pattern` | 正则匹配 `scope_url_pattern` | 跨路径限定 |
| `allowlist` | host 在 `scope_allowlist_hosts` 中 | 跨站合并任务 |

非 http(s) URL（`javascript:` / `mailto:` / `ftp:`）一律拒绝。

调用位置：
- 列表页 → 详情链接：scope 校验
- 列表页 → 翻页 URL：scope 校验（仅当 `scope_follow_pagination=True`）
- 详情页 → 解读链接：scope 校验
- 详情页 → 附件 URL：scope 校验

被拒 URL 会写入 `url_record.scope_decision='rejected_scope'`（暂以 `RunReport.rejected_by_scope` 计数）。

## 5. 递归发现（深度传播）

```
Step 1: seed entry_urls → frontier 入队（depth=0, list_page）
Step 2: while frontier 有 ready item：
  case list_page  → fetch + parse_list:
    - next_pages 入队（depth 不变 = 0）
    - detail_links 入队（depth+1 = 1）
  case detail/interpret → fetch + parse_detail + sink (crawl_raw):
    - if depth < max_depth:
        interpret_links 入队（depth+1）
        attachments 入队（depth+1，标记 fetch_only）
  case attachment → fetch + blob.put（不写 crawl_raw）
```

**max_depth 截断**：超过 `task.max_depth` 的层级不会被发现。

| max_depth | 抓取范围 |
|---|---|
| 0 | 仅 seed entry_urls 自身（极少用） |
| 1 | + 列表页发现的详情页（不含解读 / 附件） |
| 2 | + 详情页发现的解读 / 图解 / 附件 |
| 3+ | + 解读页内的更深链接（少见） |

## 6. Pagination（翻页发现）

### 6.1 类型与覆盖矩阵

| 类型 | 例子 | 谁负责 | 当前覆盖 |
|---|---|---|---|
| URL 参数翻页 | `?page=2` | adapter 调 `detect_url_param_paginator` 静态发现 | ✅ infra helper |
| 路径翻页 | `index_2.html` / `/page/2/` | adapter 调 `detect_path_paginator` | ✅ infra helper |
| createPageHTML JS 调用 | NDRC/工信部 `createPageHTML(total, cur, prefix, suffix)`；证监会 `createPageHTML(container_id, total, cur, prefix, suffix, rows)` | adapter 调 `parse_create_page_html` + `expand_create_page_html_pages` | ✅ infra helper |
| AJAX/JSON API | `GET /api/list?page=N` / `YAOWENLIEBIAO.json` | `infra/source_probe` 先发现并留 artifact；后续 runner/API source 统一抓取 | ✅ probe capability；runner 集成后续切片 |
| Cursor / 游标 | `?after=eyJ...` | adapter 自行解析 cursor 字段 | ⚠️ 同上 |
| 无限滚动 | IntersectionObserver → AJAX | render 模拟（M5+） | ❌ 暂未实现 |
| 点击"加载更多" | JS button → AJAX | render 模拟（M5+） | ❌ 暂未实现 |

### 6.2 adapter 与 helper 的协作

```python
# 推荐写法
from infra.crawl.pagination_helpers import (
    parse_create_page_html, expand_create_page_html_pages,
)

def parse_list(html, url):
    detail_links = ...
    next_pages = []
    cph = parse_create_page_html(html)
    if cph is not None:
        total, prefix, suffix = cph
        next_pages = expand_create_page_html_pages(url, total, prefix, suffix)
    return ParseListResult(detail_links=detail_links, next_pages=next_pages)
```

### 6.3 Source Probe（codegen 前置能力）

`scripts/probe_source.py` 是 codegen 的受控探查入口，输出 `probe-result.json`：

```json
{
  "verdict": "json_api",
  "entry_url": "https://www.gov.cn/yaowen/",
  "final_url": "https://www.gov.cn/yaowen/liebiao/",
  "recommended_source_url": "https://www.gov.cn/yaowen/liebiao/YAOWENLIEBIAO.json",
  "render_required": false,
  "anti_bot_detected": false,
  "signals": ["robots:status=200 parser-decided", "js_redirect:..."],
  "artifacts": [...]
}
```

verdict 语义：

| verdict | 含义 | codegen 动作 |
|---|---|---|
| `json_api` | 发现稳定、robots 允许、可回放的公开 JSON/API 响应 | 优先基于 JSON artifact 设计列表解析；优先级高于 SSR/direct HTML 与 headless |
| `static_html` | 未发现 JSON/API，入口 HTML 或 SSR 输出可直接解析 | 写 direct adapter |
| `headless_required` | JSON/API 与 direct HTML 均不足，需要渲染 | 写 red，等待 render-pool |
| `robots_disallow` | robots 拒绝或 5xx complete disallow | 写 red，不请求正文 |
| `blocked` | auth/captcha/challenge/paywall 等保护信号 | 写 red，人工审核 |
| `fetch_failed` | 网络/HTTP 错误 | 写 red 或 partial |

probe 只能把 artifact 写入 repo 内 `runtime/probe/<host_slug>/`，不得写 `/tmp`。
probe 仍使用共享 `HttpClient` 与 `RobotsChecker`；它不是绕过层。

### 6.4 不在本 spec 范围

- 启发式探测（"试 ?page=2 看是否 200 OK"）：风险大（可能与正常请求难区分）；不实现
- AI 辅助翻页发现：M3.5 codegen 启用后纳入 prompt 框架（codegen-output-contract.md §6）

## 7. 默认 priority_score 与 base_score

不同来源的 URL 默认 base_score（在 §3.2 公式里 + depth_weight 后形成最终 priority）：

| URL 来源 | discovery_source | base_score | 在 BFS max_depth=2 下的最终 priority |
|---|---|---|---|
| seed | `list_page` | 0.7 | depth=0：300.7 |
| 列表页翻页 | `list_page` | 0.7 | depth=0：300.7（与 seed 同级） |
| 列表页 → 详情 | `list_to_detail` | 0.5 | depth=1：200.5 |
| 详情页 → 解读 | `detail_to_interpret` | 0.4 | depth=2：100.4 |
| 详情页 → 附件 | `detail_to_attachment` | 0.3 | depth=2：100.3（同层略后于解读） |

> base_score 仅在同 depth 内做微调（差距 < 1）；跨 depth 的 100 分阶差远超 base，确保 BFS 不被打乱。

## 8. RunReport 完整性指标

`infra/crawl/runner.py:RunReport` 字段：

| 字段 | 含义 |
|---|---|
| `list_pages_fetched` | 列表页（含翻页）抓取次数 |
| `detail_urls_discovered` | parse_list 发现的详情 URL 总数 |
| `detail_urls_fetched` | 详情页实际抓取次数 |
| `interpret_pages_fetched` | 解读 / 图解页抓取次数 |
| `attachments_fetched` | 附件文件抓取次数 |
| `raw_records_written` | crawl_raw 新增行数 |
| `raw_records_dedup_hit` | crawl_raw url_hash 去重命中数 |
| `rejected_by_scope` | 被作用域闸口拒绝的 URL 数 |
| `rejected_by_robots` | 被 robots 拒绝的 URL 数 |
| `errors` | 错误总数 |
| `anti_bot_events` | 反爬命中次数 |
| `failures` | 错误摘要列表（前 10 条） |

完整性验收（业务层定）：
- `raw_records_written / detail_urls_discovered ≥ 95%`（关键字段命中率）
- `errors / total_fetches < 1%`
- `anti_bot_events == 0`（命中即 host disable）

## 9. 与其他 spec 的关系

| 关系 | spec |
|---|---|
| Adapter 接口约定 | `codegen-output-contract.md` §2 |
| 调度策略来源（BFS/DFS） | `research/research-ai-first-crawler-system-20260427.md` §3-§4 |
| 限流与反爬底层 | `infra-fetch-policy.md` |
| Headless 渲染池 | `infra-render-pool.md` |
| 增量抓取（HTTP 304） | `infra-resilience.md` §1 |
| Checkpoint 与续抓 | `infra-resilience.md` §2 |
| 数据落地 schema | `data-model.md` §4.2.1（url_record）、§4.2.2（fetch_record）、§4.2.3（crawl_raw） |
| Scope 字段定义 | `data-model.md` §4.1.1（task scope_*） |
| 自动合并 canary | `codegen-auto-merge.md` §4 |

## 10. 不在 v1 范围

- **多 host host_score 外层调度**：单 host 任务退化为 round-robin；多 host 任务会出现时（M3.5 多 task 并行）实现
- **AI 辅助 priority_score**：等 M3 infra/ai 接入后做（research §3 7 因子完整公式）
- **aging_bonus 防饥饿**：单 host MVP 用不上；多 host 时由 frontier 在出队时计算
- **真实 Playwright 渲染 / 滚动 / 加载更多**：M5 渲染池后续任务（TD-008，见 `infra-render-pool.md`）；当前仅支持 `RendererPool` 注入和 adapter 明确信号触发的基础 fallback。
- **AI 链接发现**：M3.5+ codegen 平台
- **Sitemap 解析**：可作为 helper 加入（`parse_sitemap`）；当前 NDRC 不需要

## 11. 验收点

- 单元：见 `tests/infra/{test_strategies, test_scope, test_pagination_helpers, test_dedup}.py`（共 ~17 用例）
- 黄金：`tests/domains/gov_policy/ndrc/test_adapter.py::test_parse_list_emits_pagination`（验证 createPageHTML 解析）
- 单元覆盖：`tests/infra/test_pagination_helpers.py` 覆盖 total-first 双/单引号与 container-id-first createPageHTML 变体
- 端到端：`scripts/run_crawl_task.py` 配 `--max-depth=2 --max-pages=15+` 跑 NDRC，期望 9 list + 数条 detail + 解读 + 附件均到位

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 6 | 2026-04-29 | `CrawlEngine` 增加 renderer 注入入口，adapter 明确 `should_render` 或解析失败 fallback 时可使用 `infra/render` 基础池；默认 disabled，不启动真实浏览器 | `infra-render-pool.md` rev 3 |
| rev 5 | 2026-04-29 | 验收点中的 NDRC golden 测试路径同步为 `tests/domains/gov_policy/ndrc/test_adapter.py` | `codegen-output-contract.md` rev 16 |
| rev 4 | 2026-04-29 | 扩展 `parse_create_page_html`，支持政府站常见的单引号 total-first 与 container-id-first 变体（如 `createPageHTML('page_div',5,1,'fg','shtml',89)`）；避免 codegen 因 helper 未覆盖而只采首页 | `pagination_helpers.py`、`test_pagination_helpers.py`、`codegen-output-contract.md` rev 13 |
| rev 3 | 2026-04-29 | 新增 `infra/source_probe` 与 `scripts/probe_source.py` 契约：codegen 先通过受控工具判断 static / JSON API / headless_required，并把 artifact 写入 `runtime/probe/`；AJAX/JSON 不再由 adapter hook 自行联网 | `codegen-output-contract.md` rev 6 |
| rev 2 | 2026-04-28 | 补充 headless render pool 的 spec 归属；CrawlEngine v1 仍不实现渲染，只把 M5 能力边界指向 `infra-render-pool.md` | TD-008 / `infra-render-pool.md` |
| rev 1 | 2026-04-28 | 初稿 —— CrawlEngine 契约 + BFS/DFS routing order + 4 scope mode + 递归发现 + 翻页 helper（cph/url_param/path）。落实 research §3-§4 与 commit 1987ac8 的引擎重构 | 替代 design-task-driven-codegen §6 的 worker 循环描述；外延 codegen-output-contract.md §2 |
