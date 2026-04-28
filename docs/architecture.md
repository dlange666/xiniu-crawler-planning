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
│   → (Renderer 按需) → Parser → Dedup → AI Extractor → Sink    │
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
│   ├── ai/                        LLM 客户端 · prompt 框架 · schema 校验
│   ├── agent/                     CodingAgentBackend 协议 · OpenCode 实现
│   ├── sandbox/                   worktree 隔离 + 文件系统白名单
│   ├── harness/                   验证框架（业务规则由 domain 注入）
│   ├── codegen/                   codegen worker 主循环 · TaskSource 抽象
│   ├── adapter_registry/          已合并 adapter 的入口点扫描与解析
│   ├── scheduler/                 定时调度 + 金丝雀池
│   └── observability/             结构化日志 · OTel（M5）
└── docs/
    ├── prod-spec/<domain>.md       业务规格（先于 domain 建立）
    └── architecture.md             本文件
```

判定 "属于 infra 还是 domain" 的简单准则——这段逻辑能被另一个业务域原样
复用吗？能则 `infra/`，否则 `domains/`。

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
- **去重位置**：source 层不去重；解析层用联合键严格去重；simhash 仅作信号。
- **存储抽象**：`infra/storage/` 通过 `STORAGE_PROFILE=dev|prod` 切换；dev=SQLite+本地 FS，prod=PolarDB+阿里云 OSS。
- **反爬合规与限流/重试**：robots 入口前置；命中 challenge/captcha/WAF/auth → cooldown + 人工，**不重试不绕过**。完整契约（限流参数、重试矩阵、反爬识别信号、紧急止损阈值）见 `docs/prod-spec/infra-fetch-policy.md`。
- **韧性与增量**：已 spec 化 `docs/prod-spec/infra-resilience.md`（HTTP 条件请求 + checkpoint + 版本巡检 + DLQ）；**MVP 暂缓实施**（TD-010/011/012）。
- **可观测性**：已 spec 化 `docs/prod-spec/infra-observability.md`（零自建后台版：metric_snapshot + cron 告警 + LiteLLM 成本）；**MVP 暂缓实施**（TD-013）。
- **可视化**：已 spec 化 `docs/prod-spec/infra-visualization.md`（FastAPI + Jinja2 + Chart.js 自建轻量看板，可嵌入 master 进程）；**MVP 暂缓实施**（TD-014）。
- **部署形态**：已 spec 化 `docs/prod-spec/infra-deployment.md`（**主从分布**；自建分发系统 `infra/dispatch/`；HTTP+JSON 协议；不用 Airflow/Celery/Kafka）；MVP 单进程跑通，扩展期升级（TD-015）。
- **代码生成默认 agent**：OpenCode CLI（`opencode run` 一次性子进程）；`infra/agent/` 提供抽象，可替换为 ClaudeCode / Codex / Mock；模型 ID 为参数。
- **Task API 边界**：Task 提交、持久化、状态查询在**外部独立项目**；本仓库仅做 codegen 消费端 + 执行端。
- **adapter 路径**：`domains/<context>/adapters/<host>.py` 一层文件，不嵌套在 `parse/sites/` 下，也不放仓库顶层。
- **跳过人审的安全网**：分级合并 tier 1/2/3 + 加压 harness（golden ≥10、E2E ≥20、schema ≥98%、关键字段 ≥99%）+ 4 档渐进 canary + 自动回滚 + IM 审计；tier-3 路径永远人审。详见 `docs/prod-spec/codegen-auto-merge.md`。
- **限流分级启动（warm-up）**：新 host / canary 流量按 4 级阶梯（10%/30%/60%/100%）放开，反爬命中即降到 L0+cooldown。详见 `docs/prod-spec/infra-fetch-policy.md` §2.3。

## 6. 与研究报告的偏离

- 不引入 etcd/Kafka：MVP 单进程 + SQLite；扩到多 worker 时再评估 Redis/RabbitMQ。
- 不接入邮件、PDF→文本、simhash 自动合并、多租户、删除链路（详见 `docs/exec-plan/tech-debt-tracker.md`）。
