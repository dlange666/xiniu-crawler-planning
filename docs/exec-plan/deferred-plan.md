# 暂缓计划（Deferred Plans）

收录"已完成详细设计但暂不实施"的 plan。每个 plan 一个二级章节；何时启用
由 `Planner` 显式决定。

## 与 `tech-debt-tracker.md` 的区别

| 文档 | 内容粒度 | 何时用 |
|---|---|---|
| `tech-debt-tracker.md` | 1 行登记（标题 + 风险 + 状态） | 还没做完整设计的债务 |
| 本文件章节 | 完整 plan（任务列表 + 验收 + 边界） | **设计已经做完**但用户决定暂不实施 |

提升流程：本文件中某节内容整体提升 → 复制到 `active/plan-<date>-<slug>.md`
→ 本文件该节删除 + cleanup-log 记录 + tech-debt 对应 TD 升级。

---

## plan-20260428-observability-bootstrap

### 元信息

- **Plan ID**：`plan-20260428-observability-bootstrap`
- **关联规格**：`docs/prod-spec/infra-observability.md`（零自建后台版）、`docs/prod-spec/infra-resilience.md`
- **状态**：`deferred`（不进入 MVP；MVP 跑稳后由 Planner 决定何时提升）。登记 TD-013
- **里程碑**：M-Observability（≈1.5 周）

### 目标

交付**零自建后台服务**的最小可观测性：所有指标存到与业务同一个 DB，
告警靠 cron + SQL + IM webhook，无 Prometheus / Alertmanager / Grafana。
后续公司基础设施就位（TD-005），仅替换 `recorder.py` 一个文件即可升级。

### 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式 | 状态 |
|---|---|---|---|---|---|
| T-20260428-301 | [infra/observability] recorder + snapshot flusher | `infra-observability.md` §3, §4 | `infra/observability/recorder.py` 提供 `incr/observe/set` API（接口与 prometheus-client 兼容）；进程内聚合；每 60s flush 到 `metric_snapshot` 表（按 `infra-observability.md` §3）；按 §4 注册 8 个采集负载指标；与 frontier、http、parse hook 点连接 | 单元测试：跑 fake 任务后查表得到 8 个指标；recorder 接口签名与 prometheus-client 等价 | `pending` |
| T-20260428-302 | [scripts] OSS 用量轮询 | `infra-observability.md` §5 | `scripts/observe_oss_usage.py`：调阿里云 OSS API 按 `infra-observability.md` §5 写入 4 个指标到 metric_snapshot；外部 cron 每小时触发；月成本估算公式从配置读 | 单元测试：mock OSS 响应；月成本与字节数同方向；运行后 metric_snapshot 有对应行 | `pending` |
| T-20260428-303 | [infra/ai] LiteLLM gateway 接入 + 成本指标 | `infra-observability.md` §6 | `infra/ai/llm_client.py` 默认走 LiteLLM（OpenAI 兼容协议指向 `LITELLM_BASE_URL`），透传 `x-litellm-tags=task=...,context=...`；`scripts/observe_llm_spend.py` 每 10min 调 `/spend/get` 写入 6 个指标；预算守门按 §6 三档生效（剩余 < 20%/5%/0%） | 单元测试：mock LiteLLM；标签透传正确；预算三档行为正确；指标写表 | `pending` |
| T-20260428-304 | [scripts] 告警脚本 + IM webhook | `infra-observability.md` §7 | `scripts/observe_check.py`：按 `infra-observability.md` §7 跑 8 条告警 SQL；命中即 POST 到 `OBSERVE_WEBHOOK_URL`（钉钉/飞书/企微）；payload 格式见 §7；外部 cron 每 5min 触发 | 单元测试：注入超阈值数据 → webhook 收到正确 payload；空数据不触发；webhook 故障不影响主流程 | `pending` |
| T-20260428-305 | [docs/eval-test] M-Observability 验收 | — | 用一个跑 24h 的小流量任务作为基线；查询 metric_snapshot 与告警历史；写入 `docs/eval-test/` 报告 | 工件含 18 个指标的真实数值 + 至少一次告警 webhook 投递记录 | `pending` |

### 边界护栏

- **不部署** Prometheus / VictoriaMetrics / Alertmanager / Grafana / Loki。
- **不暴露** `/metrics` HTTP endpoint（升级时再加）。
- **不引入**新的 LLM 客户端实现路径；执行面 LLM 调用统一走 LiteLLM gateway。
- **不绕过** LiteLLM 后台预算；提权走 LiteLLM 后台。
- **不让** webhook 故障影响止损：所有自动止损动作（暂停 host、disable adapter）由进程内 frontier/anti-bot 直接触发，与 webhook 链路解耦。

### 完成标准（提升后启用）

`green` 仅当：

- 第 3 节 5 个任务全部 `completed`
- T-20260428-305 工件展示 18 个指标在 24h 真实样本下有数值
- LiteLLM 后台已配置至少一个 `business_context` 的月度预算
- 至少一次告警 webhook 端到端跑通（钉钉/飞书/企微任一）

### 后续升级路径（不在本 plan 内）

公司有 Prometheus 拉取端后：

1. 在 `recorder.py` 加 `PrometheusBackend`，与 `DBSnapshotBackend` 并存（环境变量切换）
2. 暴露 `/metrics`，运维加 scrape config
3. cron+SQL 告警渐进迁移到 PrometheusRule
4. `metric_snapshot` 表保留 90d 后退役

升级期间业务代码完全不动。

---

## plan-20260428-render-pool-bootstrap

### 元信息

- **Plan ID**：`plan-20260428-render-pool-bootstrap`
- **关联规格**：`docs/prod-spec/infra-render-pool.md`、`docs/prod-spec/infra-crawl-engine.md`、`docs/prod-spec/infra-fetch-policy.md`
- **状态**：`deferred`（M5；登记 TD-008）
- **里程碑**：M5 调度 + 反爬 + 渲染（≈2 周，嵌入 M5 总计划）

### 目标

交付单进程、保守默认值的 headless render pool，让 JS 渲染站点在不绕过保护
措施的前提下可采、可限流、可回放、可观测。它只作为 static/API/SSR 之后的
末档 fallback，不进入所有请求主路径。

### 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式 | 状态 |
|---|---|---|---|---|---|
| T-20260428-401 | [infra/render] 类型与 render decision gate | `infra-render-pool.md` §3, §4 | 新建 `infra/render/{types,decision,config}.py`；实现 `RenderRequest` / `RenderResult` / `RenderDecision`；覆盖允许矩阵和禁止矩阵；默认 `RENDER_POOL_ENABLED=false` | 单元测试：JS shell 允许；API 可用不渲染；robots/login/captcha/challenge/paywall 禁止 | `pending` |
| T-20260428-402 | [infra/render] Playwright BrowserPool | `infra-render-pool.md` §4, §5, §7 | 新建 `infra/render/pool.py` 与 `playwright_backend.py`；实现全局并发、per-host 并发、timeout、max_bytes、context 回收和 browser crash 重建 | 单元测试 + fake backend：并发不超限；timeout / crash / bytes_exceeded error_kind 正确 | `pending` |
| T-20260428-403 | [infra/crawl] CrawlEngine render fallback 接入 | `infra-render-pool.md` §2, §6；`infra-crawl-engine.md` §5 | runner 在静态 fetch + parse 失败或 adapter `should_render` 命中后调用 renderer；`fetch_record.rendered=1`；render DOM 通过 BlobStore 落盘并进入 parse | 集成测试：受控 JS fixture 静态失败、render 后写入 `crawl_raw`；NDRC direct 路径不触发 render | `pending` |
| T-20260428-404 | [infra/render + frontier] render queue 与 backlog 回压 | `infra-render-pool.md` §5, §8 | 新建单进程 render queue；接入 host cooldown、task render budget、`RENDER_QUEUE_MAX_SIZE`；队列满时低优先级 URL 延后或 DLQ，普通 HTTP 不阻塞 | 单元测试：queue full 后 HTTP 队列继续；per-host cooldown 共享；budget 耗尽不再 render | `pending` |
| T-20260428-405 | [infra/harness] headless 合规扫描与 adapter 门槛 | `infra-render-pool.md` §3, §10；`codegen-output-contract.md` §2.3 | harness 禁止 `stealth`、`captcha_solver`、`undetected_chromedriver` 等；`render_mode=headless` adapter 必须提供 `should_render` 或 fixture 证明；challenge fixture 判 red | 单元测试：违规词拦截；缺少 render 证据拦截；challenge 不渲染 | `pending` |
| T-20260428-406 | [docs/eval-test] Render Pool 验收 fixtures | `infra-render-pool.md` §11 | 增加受控 fixtures：JS shell、无限滚动简化页、captcha/challenge、robots disallow、browser crash；写 `docs/eval-test/render-pool-20260428.md` | Eval 工件含每个 fixture 的 green/red 证据；真实 JS 站点小样本 `raw_records_written >= 1` | `pending` |

### 边界护栏

- **不做** captcha solver、滑块、人类行为模拟、stealth 指纹伪装。
- **不做** 自动登录、凭据管理、付费墙访问。
- **不做** 代理轮换或为绕过保护而切出口。
- **不做** 分布式 render farm；v1 仅单进程池，扩容另立 plan。
- **不让** headless 成为默认路径；必须有 render decision reason。
- **不放宽** `infra-fetch-policy.md` 中 robots、Retry-After、cooldown、warm-up 的约束。

### 完成标准（提升后启用）

`green` 仅当：

- 第 3 节 6 个任务全部 `completed`
- `RENDER_POOL_ENABLED=false` 时所有 headless adapter 均显式拒绝，不静默降级
- 受控 JS shell fixture 能 render 后入库，challenge / robots fixture 均不渲染
- `fetch_record.rendered=1`、render DOM blob、decision reason 与指标可回放
- NDRC 等 direct adapter 回归不触发 renderer，原有测试全绿
