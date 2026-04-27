# 架构

本文件只描述**仓库级 high-level 架构**：分层、目录结构、依赖规则、几条
关键决策。具体业务域的子模块拆分、字段、流水线编排写在对应
`docs/prod-spec/<domain>-<vN>.md`。详细论证见
`docs/research/research-ai-first-crawler-system-20260427.md`。

## 1. 分层

```
┌─────────────────────── Control Plane · 自研 ───────────────────────┐
│  Task API  ──→  Policy/Scope  ──→  Frontier  ──→  Lease/Shard       │
└────────────────────────────┬────────────────────────────────────────┘
                             ▼  派发
┌─────────────────────── Data Plane · 复用成熟组件 ──────────────────┐
│                                                                      │
│   Fetcher ──→ (Renderer 按需) ──→ Parser ──┬─→ Dedup(解析层) ──┐    │
│                                            │                    │    │
│                                            └─→ AI Extractor ────┤    │
│                                                                 ▼    │
│                                                    Sink ──→ Store    │
│                                                  (PolarDB · OSS · ES)│
└──────────────────────────────────────────────────────────────────────┘
```

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
│   └── observability/             结构化日志 · OTel（M5）
└── docs/
    ├── prod-spec/<domain>-<vN>.md  业务规格（先于 domain 建立）
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
- **反爬合规**：robots 入口前置；命中 challenge/captcha/WAF/auth → cooldown + 人工，**不重试不绕过**。
- **可观测性**：结构化日志先行，OTel/Grafana 推迟到 M5（TD-005）。

## 6. 与研究报告的偏离

- 不引入 etcd/Kafka：MVP 单进程 + SQLite；扩到多 worker 时再评估 Redis/RabbitMQ。
- 不接入邮件、PDF→文本、simhash 自动合并、多租户、删除链路（详见 `docs/exec-plan/tech-debt-tracker.md`）。
