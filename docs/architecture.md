# 架构

本文件只描述**仓库级 high-level 架构**：分层、目录结构、依赖规则、几条
关键决策。具体业务域的子模块拆分、字段、流水线编排写在对应
`docs/prod-spec/<domain>.md`。详细论证见
`docs/research/research-ai-first-crawler-system-20260427.md`。

## 1. 分层（双平面）

```
[外部独立项目] Task API + Task Store  ──┐
                                          │ HTTP / 协议待定
                                          ▼
┌─────────── Code-Gen Plane（离线，infra/）──────────┐
│  Codegen Worker → Sandbox → Coding Agent           │
│       (OpenCode CLI · 模型为参数)                   │
│             ↓                                       │
│        Verification Harness                         │
│             ↓                                       │
│        gh pr create → 人审 → merge                  │
└──────────┬──────────────────────────────────────────┘
           │ 已合并 adapter
           ▼
┌─────────── Execution Plane（在线，infra/ + domains/）─────────┐
│   Scheduler → Adapter Registry → Frontier → Fetcher           │
│   → (Render Pool 按需) → Parser → Dedup → AI Extractor → Sink │
│   → PolarDB / OSS / ES                                         │
└───────────────────────────────────────────────────────────────┘
```

- 两个平面通过仓库 `main` 串联：**合入即上线**。
- Task 来源是外部独立项目；本仓库只承担消费端 + 执行端。
- 控制面自研；数据面复用成熟组件。
- AI 不进入请求主路径，仅出现在高不确定决策点（页面分类、字段抽取、URL 排序、反爬识别）。

## 2. 目录结构

```
xiniu-crawler/
├── domains/                       业务域（bounded contexts）
│   ├── gov_policy/                ─ 第一阶段建设中
│   ├── exchange_policy/           ─ 计划
│   └── oversea_policy/            ─ 计划
├── infra/                         跨域技术能力（不含业务规则）
│   ├── storage/                   PolarDB / SQLite / OSS / 本地 FS 抽象
│   ├── http/                      HTTP 客户端 · UA · Retry-After · 令牌桶
│   ├── robots/                    RFC 9309
│   ├── frontier/                  两级队列 · 三类令牌
│   ├── render/                    Playwright headless 渲染池（按需，M5）
│   ├── ai/                        LLM 客户端 · prompt 框架 · schema 校验
│   ├── agent/                     CodingAgentBackend 协议 · OpenCode 实现
│   ├── sandbox/                   worktree 隔离 + 文件系统白名单
│   ├── harness/                   验证框架（业务规则由 domain 注入）
│   ├── codegen/                   codegen worker 主循环 · TaskSource 抽象
│   ├── adapter_registry/          已合并 adapter 的入口点扫描与解析
│   ├── scheduler/                 定时调度 + 金丝雀池
│   └── observability/             结构化日志 · OTel（M5）
├── webui/                         任务后台 + 采集监控 + 结果浏览（FastAPI API + React）
└── docs/
    ├── prod-spec/<domain>.md       业务规格（先于 domain 建立）
    └── architecture.md             本文件
```

判定 "属于 infra 还是 domain" 的简单准则——这段逻辑能被另一个业务域原样
复用吗？能则 `infra/`，否则 `domains/`。

### 2.1 Capability × Spec × Plan 对照表

按"能力域 → 由哪份 spec 定契约 → 由哪个 plan 实施 → 由哪些代码模块承载"
横向看清整体。新增能力时，先在本表加一行（spec 必须先存在，plan 与代码可后续）。

| 能力域 | 主 spec | 实施 plan | 代码落点 | 状态 |
|---|---|---|---|---|
| 通用爬虫引擎 | `prod-spec/infra-crawl-engine.md` | `plan-20260427-mvp-policy-crawler` T-20260427-106..T-20260427-109 | `infra/crawl/` | MVP 已实现核心（rev 1） |
| 政策业务规格 | `prod-spec/domain-gov-policy.md` | `plan-20260427-mvp-policy-crawler` (M1–M3) | `domains/gov_policy/adapters/` + seeds + golden | MVP 实施 |
| 数据模型 | `prod-spec/data-model.md` | 各 plan 中相关 task 共同实施 | `infra/storage/` 建表脚本 | MVP 实施 |
| 限流 / 重试 / 反爬识别 / warm-up | `prod-spec/infra-fetch-policy.md` | `plan-20260427-mvp-policy-crawler` T-20260427-103/T-20260427-104/T-20260427-105；`plan-20260428-codegen-bootstrap` T-20260428-216 | `infra/http/`、`infra/robots/`、`infra/frontier/` | MVP 实施 |
| Headless 渲染池 | `prod-spec/infra-render-pool.md` | `deferred-plan.md`（plan-20260428-render-pool-bootstrap，TD-008） | `infra/render/`、`infra/crawl/runner.py` | M5 暂缓 |
| 韧性（增量 / checkpoint / 异常分级 / 心跳） | `prod-spec/infra-resilience.md` | 暂缓（TD-010/011/012） | `infra/checkpoint/`、`infra/version_guard/`（待建） | 暂缓 |
| 部署 / 自建分发 | `prod-spec/infra-deployment.md` | 暂缓（TD-015） | `infra/dispatch/`（待建） | MVP 单进程；扩展期升级 |
| 可观测（指标 / 告警 / 成本） | `prod-spec/infra-observability.md` | `deferred-plan.md`（plan-20260428-observability-bootstrap，TD-013） | `infra/observability/`、`infra/ai/budget.py`（待建） | 暂缓 |
| Webui · 任务后台 + 监控 + 浏览 | `prod-spec/webui.md` | `plan-20260428-webui-bootstrap` T-20260428-301/T-20260428-302 | `webui/` + `webui/frontend/` | React + Ant Design Pro 重写中（OAuth 暂缓 TD-018） |
| Codegen 平台 · adapter 输出契约 | `prod-spec/codegen-output-contract.md` | `plan-20260428-codegen-bootstrap` T-20260428-201/T-20260428-203/T-20260428-206 | `infra/agent/`、`infra/harness/`、`infra/adapter_registry/`（M3.5） | M3.5 实施 |
| Codegen 平台 · 自动合并安全网 | `prod-spec/codegen-auto-merge.md` | `plan-20260428-codegen-bootstrap` T-20260428-202/T-20260428-207/T-20260428-212..T-20260428-215 | `infra/sandbox/`、`infra/scheduler/`、`infra/codegen/`（M3.5） | M3.5 实施 |

> 暂缓能力的 spec 是已通过的设计契约，仅 plan 暂未启动。提升时把 plan 从
> `deferred-plan.md` / TD-X 升到 `active/`。

## 3. 依赖规则

```
domains/<X>/*  ───→  infra/*                       ✓
domains/<A>/*  ─ ✗ ─→  domains/<B>/*               业务域之间禁止
infra/*        ─ ✗ ─→  domains/*                   反向禁止
domains/<X>/<a> ──→ domains/<X>/<b>                仅当 spec 显式声明
```

业务域内部子模块的依赖关系由该域 spec 显式声明。后续加 import-linter 守护。

## 4. 数据流（一条政策的生命周期）

```
  User / Cron
       │ 提交 seed 任务
       ▼
   Task API ──→ Frontier ──(派发 URL)──→ Fetcher
                                             │
                              ┌──────────────┼─────────────┐
                              ▼              ▼             ▼
                          原始字节         HTML/        元数据
                              │           元数据           │
                              ▼              │             │
                            Sink ─→ OSS      ▼             │
                                          Parser ──────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              │              ▼
                            Dedup            │         AI Extractor
                          (联合键)           │       (36 字段 JSON)
                              │              │              │
                              └──────────────┼──────────────┘
                                             ▼
                                           Sink ──→ PolarDB
```

## 5. 关键决策

- **抓取层级顺序**：`feed/sitemap → static → 接口拦截 → SSR/DOM → headless 渲染`，按信号递进。
- **Headless 渲染池**：已 spec 化 `docs/prod-spec/infra-render-pool.md`。它只在 static/API/SSR 均不足且命中明确渲染信号时启用；禁止用于验证码、登录、付费墙、technical challenge 或 robots 拒绝站点。MVP/M3.5 仍保持 `render_mode=headless` 显式拒绝，M5 提升 TD-008 后实现。
- **去重位置**：source 层不去重；解析层用联合键严格去重；simhash 仅作信号。
- **存储抽象**：`infra/storage/` 通过 `STORAGE_PROFILE=dev|prod` 切换；dev=SQLite+本地 FS，prod=PolarDB+阿里云 OSS。
- **反爬合规与限流/重试**：robots 入口前置；命中 challenge/captcha/WAF/auth → cooldown + 人工，**不重试不绕过**。完整契约（限流参数、重试矩阵、反爬识别信号、紧急止损阈值）见 `docs/prod-spec/infra-fetch-policy.md`。
- **韧性与增量**：已 spec 化 `docs/prod-spec/infra-resilience.md`（HTTP 条件请求 + checkpoint + 版本巡检 + DLQ）；**MVP 暂缓实施**（TD-010/011/012）。
- **可观测性**：已 spec 化 `docs/prod-spec/infra-observability.md`（零自建后台版：metric_snapshot + cron 告警 + LiteLLM 成本）；**MVP 暂缓实施**（TD-013）。
- **Webui（任务后台 + 采集监控 + 结果浏览）**：spec `docs/prod-spec/webui.md` rev 12。FastAPI 提供 `/api/*`、鉴权和审计，并托管 `/ui` React SPA；前端位于 `webui/frontend/`，使用 React + TypeScript + Vite + Ant Design ProComponents。任务详情页用单个 URL 列表 + Tabs 切换“全部 / 已采集 / 未采集”，以 `crawl_raw` 是否存在定义采集状态；列表只显示操作按钮/状态，正文在站内 `crawl_raw` 详情页展示，不直接跳转源站。采集详情页展示正文、入库信息、metadata，详情页发现的 depth+1 子链接直接展开在 `Attachments` 下，附件优先显示文件名。鉴权用 `AuthBackend` 抽象（MVP 用 `DevBackend` 免登；OAuth/OIDC 暂缓 TD-018），不在本仓库存储凭据；写操作落 `crawl_task.created_by` + `webui_audit` 表。
- **部署形态**：已 spec 化 `docs/prod-spec/infra-deployment.md`（**主从分布**；自建分发系统 `infra/dispatch/`；HTTP+JSON 协议；不用 Airflow/Celery/Kafka）；MVP 单进程跑通，扩展期升级（TD-015）。
- **通用爬虫引擎**：`infra/crawl/` 承担 BFS/DFS 调度、scope 闸口、递归发现、翻页 helper；business-agnostic、由 adapter resolver 注入业务。详见 `docs/prod-spec/infra-crawl-engine.md`。
- **Routing order**：层内近似 BFS + 全局优先级堆（research §3-§4）。priority = depth_weight + base_score；列表页 base 0.7、详情 0.5、解读 0.4、附件 0.3——预算耗尽时浅层先收齐。
- **代码生成默认 agent**：OpenCode CLI（`opencode run` 一次性子进程）；`infra/agent/` 提供抽象，可替换为 ClaudeCode / Codex / Mock；模型 ID 为参数。
- **Task API 边界**：codegen 的 Task 提交、持久化、状态查询在**外部独立项目**；本仓库仅做 codegen 消费端。WebUI MVP 维护采集任务后台所需的 `crawl_task` / `crawl_task_execution` 子集，与 codegen 外部 TaskSource 不混用。
- **adapter 路径**：`domains/<context>/adapters/<host>.py` 一层文件，不嵌套在 `parse/sites/` 下，也不放仓库顶层。
- **跳过人审的安全网**：分级合并 tier 1/2/3 + 加压 harness（golden ≥10、E2E ≥20、schema ≥98%、关键字段 ≥99%）+ 4 档渐进 canary + 自动回滚 + IM 审计；tier-3 路径永远人审。详见 `docs/prod-spec/codegen-auto-merge.md`。
- **限流分级启动（warm-up）**：新 host / canary 流量按 4 级阶梯（10%/30%/60%/100%）放开，反爬命中即降到 L0+cooldown。详见 `docs/prod-spec/infra-fetch-policy.md` §2.3。

## 6. 与研究报告的偏离

- 不引入 etcd/Kafka：MVP 单进程 + SQLite；扩到多 worker 时再评估 Redis/RabbitMQ。
- 不接入邮件、PDF→文本、simhash 自动合并、多租户、删除链路（详见 `docs/exec-plan/tech-debt-tracker.md`）。
