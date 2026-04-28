# Infra Headless Render Pool · 按需浏览器渲染池

> **版本**：rev 1 · **最近修订**：2026-04-28 · **状态**：active
> **实施状态**：M5 暂缓（TD-008；计划见 `docs/exec-plan/deferred-plan.md#plan-20260428-render-pool-bootstrap`）。当前代码只允许 adapter 声明 `render_mode=headless`，`CrawlEngine` 会显式拒绝执行，避免误以为已支持。

> 本 spec 定义 `infra/render/` 的长期契约：headless 只能作为抓取层级末档的
> 按需能力，服务 JS 渲染站点、无限滚动与"加载更多"等静态 HTML / JSON API
> 无法覆盖的场景。它不是反爬绕过工具，也不进入所有请求主路径。

## 1. 范围

| 覆盖 | 说明 |
|---|---|
| Render decision | 判断某个 URL 是否允许进入 headless 渲染 |
| Render queue | 在 `frontier` 之后独立排队，接受任务预算、host 限流和 backlog 回压 |
| Browser pool | Playwright 驱动的浏览器 / context / page 池，控制并发、超时和崩溃回收 |
| Crawl integration | `infra/crawl/runner.py` 在静态抓取、API 探查或 adapter 信号之后调用 renderer |
| Raw retention | 渲染前后的原始字节、最终 DOM 快照与 HTTP 元数据必须可回放 |
| Observability | render backlog、成功率、耗时、崩溃、成本与合规事件 |

不覆盖业务解析规则。业务域仍只通过 adapter hook 暴露 `parse_list` /
`parse_detail` / `should_render` 等纯函数。

## 2. 原则

| 原则 | 契约 |
|---|---|
| 层级递进 | 严格遵循 `feed/sitemap -> static HTML -> JSON/API -> SSR/DOM -> headless` |
| 按需渲染 | 只有命中 §3 的信号才进入 render queue；默认不渲染 |
| 合规优先 | robots 拒绝、登录、验证码、付费墙、technical challenge 一律不渲染重试 |
| 真实身份 | 浏览器请求必须携带项目身份与联系信息；不得使用 stealth / 指纹伪装 |
| 资源隔离 | render 与 HTTP fetcher 分池限流，不能吃掉普通抓取预算 |
| 可回放 | 渲染输入、主响应、最终 DOM、网络摘要和错误必须能关联到 task/run/url |

## 3. Render Decision

### 3.1 允许进入渲染的信号

| 信号 | 触发者 | 处理 |
|---|---|---|
| `ADAPTER_META.render_mode == "headless"` | adapter registry | URL 进入 render decision；仍需先过 robots 与反爬检查 |
| `should_render(html, url) == True` | adapter 可选 hook | 进入 render queue |
| 静态 HTML 为 JS shell | 通用 decision | 例如正文容器为空、脚本 bundle 占比高、目标选择器缺失 |
| 静态 parse 失败但无反爬信号 | `infra/crawl` | 允许一次 render fallback；失败后进 DLQ / fix-task |
| 翻页类型为无限滚动 / 点击加载更多 | adapter 或 codegen harness | 进入 render queue，按任务页数上限截断 |

### 3.2 禁止进入渲染的信号

| 信号 | 处理 |
|---|---|
| robots disallow / robots 5xx complete disallow | 直接拒绝，不渲染 |
| 401 / 403 / 登录跳转 / auth-required | host cooldown + 人工审核，不渲染 |
| captcha / recaptcha / hcaptcha / challenge iframe | host cooldown + 人工审核，不渲染 |
| 付费墙 / 订阅墙 | 标记 `blocked_by_policy`，不渲染 |
| API 已稳定可用 | 优先 JSON/API，不渲染 |

render decision 必须输出 `RenderDecision(allowed, reason, blocked_policy)`，并把
`reason` 写入日志 / 指标 / eval 工件，避免"为什么渲染"不可追溯。

## 4. 模块与接口

推荐模块：

```
infra/render/
├── types.py                 RenderRequest / RenderResult / RenderDecision
├── decision.py              通用 render 判定（业务 adapter 可追加信号）
├── pool.py                  RendererPool 协议 + 资源预算
├── playwright_backend.py    Playwright 实现
├── queue.py                 单进程 render queue + backlog 回压
└── config.py                保守默认值与环境变量读取
```

核心类型：

```python
@dataclass(frozen=True)
class RenderRequest:
    task_id: int
    run_id: str
    url: str
    host: str
    depth: int
    discovery_source: str
    reason: str
    timeout_ms: int
    wait_until: str
    wait_for_selector: str | None = None
    max_bytes: int | None = None


@dataclass(frozen=True)
class RenderResult:
    final_url: str
    status_code: int | None
    html: bytes
    rendered: bool
    elapsed_ms: int
    content_type: str | None
    network_summary: dict
    error_kind: str | None = None
    error_detail: str | None = None
    anti_bot_signal: str | None = None
```

`RendererPool.render(request)` 必须是单 URL 幂等调用：调用方可重试同一 URL，
sink 仍按 `url_hash` / `content_sha256` 去重。

## 5. 资源预算与默认值

`infra/render/config.py` 集中暴露默认值。环境变量只能收紧预算，不得放宽合规门槛。

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `RENDER_POOL_ENABLED` | `false` | 未显式启用时 `render_mode=headless` 仍拒绝执行 |
| `RENDER_MAX_CONCURRENCY` | `2` | 全局并发 page 数 |
| `RENDER_MAX_CONTEXTS` | `2` | 浏览器 context 上限 |
| `RENDER_PER_HOST_CONCURRENCY` | `1` | 单 host 并发 |
| `RENDER_QUEUE_MAX_SIZE` | `100` | 超过后低优先级 URL 进入 backpressure |
| `RENDER_PAGE_TIMEOUT_MS` | `15000` | 单页硬超时 |
| `RENDER_WAIT_UNTIL` | `domcontentloaded` | 默认不等到 network idle |
| `RENDER_MAX_BYTES` | `5242880` | 单页 DOM 快照上限 5 MB |
| `RENDER_MAX_PAGES_PER_TASK` | `min(50, task.max_pages_per_run * 0.2)` | 防止渲染吃掉任务预算 |

上线策略：

1. 全新 host 先按 `infra-fetch-policy.md` §2.3 warm-up 的 L0 进入。
2. 渲染命中 429/5xx 或 anti-bot 时，render queue 与 fetcher 共享 host cooldown。
3. backlog 超阈值时暂停新增 render fallback，普通 HTTP 抓取不受影响。

## 6. 存储与回放

渲染不能破坏"原始层与解析层分离"：

| 产物 | 存放 | 要求 |
|---|---|---|
| 静态主响应 | `BlobStore` | 若存在静态预抓，保留原始 body 与 HTTP metadata |
| 渲染最终 DOM | `BlobStore` | 作为本次 parse 的输入；`crawl_raw.raw_blob_uri` 指向该快照 |
| 网络摘要 | `crawl_raw.data.render.network_summary` 或 run artifact | 记录主请求、XHR 数量、最终 URL、截断状态 |
| fetch metadata | `fetch_record` | `rendered=1`，记录状态码、字节数、耗时、错误 |
| decision reason | `crawl_raw.data.render.reason` / 指标 label | 用于审计与后续调参 |

v1 不新增 DDL；若 M5 实施时发现 `crawl_run_log` 无法承载列表页 render
artifact 关联，必须先按 `data-model.md` 的权威流程补 schema，再写代码。

## 7. 错误与降级

| error_kind | 含义 | 动作 |
|---|---|---|
| `render_timeout` | 超过 `RENDER_PAGE_TIMEOUT_MS` | URL 失败；同 host 不立即重试 |
| `browser_crash` | browser / context / page 异常退出 | 回收 browser；URL 可按 retry 策略重试一次 |
| `render_queue_full` | backlog 超阈值 | 低优先级 URL 延后或 DLQ |
| `render_bytes_exceeded` | DOM 超过 `RENDER_MAX_BYTES` | 截断并标记，默认不 parse |
| `anti_bot_challenge` | 渲染后命中 challenge/captcha | host cooldown + 人工审核，不继续渲染 |
| `blocked_by_policy` | 登录 / 付费墙 / robots | 不重试 |

renderer 不负责绕过错误；它只负责把错误分类清楚并交还 frontier / resilience
层处理。

## 8. 可观测指标

M5 实施时必须纳入 `infra-observability.md` 的 recorder：

| 指标 | 类型 | 标签 |
|---|---|---|
| `crawler_render_requests_total` | counter | task, host, reason, result |
| `crawler_render_latency_ms` | histogram | task, host |
| `crawler_render_queue_depth` | gauge | task |
| `crawler_render_backlog_oldest_ms` | gauge | task |
| `crawler_render_browser_crash_total` | counter | host |
| `crawler_render_bytes_total` | counter | task, host |
| `crawler_render_blocked_total` | counter | host, blocked_policy |
| `crawler_render_pool_in_use` | gauge | pool |

WebUI / monitor 只展示这些指标，不直接驱动 render 决策。

## 9. 与其他 spec 的关系

| 关系 | spec |
|---|---|
| 抓取层级顺序、BFS/DFS 调度 | `docs/prod-spec/infra-crawl-engine.md` |
| robots / Retry-After / anti-bot cooldown | `docs/prod-spec/infra-fetch-policy.md` |
| checkpoint / DLQ / 版本巡检 | `docs/prod-spec/infra-resilience.md` |
| render 指标记录 | `docs/prod-spec/infra-observability.md` |
| adapter `render_mode` / `should_render` | `docs/prod-spec/codegen-output-contract.md` |
| raw / fetch 表权威 DDL | `docs/prod-spec/data-model.md` |

## 10. 不在本 spec 范围

- captcha solver、滑块、人类行为模拟、stealth 指纹伪装
- 自动登录、凭据管理、付费墙访问
- 代理池轮换或为绕过保护而切换出口
- 分布式 render farm / Kubernetes 独立节点池（M5 v1 先单进程池；扩容另立 plan）
- PDF 文本抽取（TD-001）
- AI 自动点击或多步网页操作

## 11. 验收点

- 单元：decision gate 覆盖允许 / 禁止矩阵；资源预算与 per-host 并发生效。
- 集成：受控 JS shell fixture 静态 parse 失败、render 后成功；challenge fixture 不进入 render。
- 端到端：一个真实 JS 渲染政策站点在 `RENDER_POOL_ENABLED=true` 下写入 `crawl_raw`，`fetch_record.rendered=1`，原始 DOM 可回放。
- 合规：禁词扫描覆盖 `stealth` / `captcha_solver` / `undetected_chromedriver` 等；robots disallow 不渲染。
- 回压：模拟 `RENDER_QUEUE_MAX_SIZE` 命中后普通 HTTP URL 仍继续推进。

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 1 | 2026-04-28 | 初稿 —— 定义 headless render pool 的触发矩阵、池化接口、预算默认值、存储回放、错误降级和观测指标；补齐 TD-008 从"backlog 阈值"到完整 infra 能力的规划 | TD-008 / `plan-20260428-render-pool-bootstrap` |
