# docs/prod-spec/ —— 产品与基础设施规格索引

本目录存放仓库的"长期参考"规格文档。每份 spec 都是该领域**已通过的设计契约**。

## 命名约定

- **kebab-case**，**不带版本号**（版本走 frontmatter + `## 修订历史`）
- 业务 spec：`<domain>.md`（如 `domain-gov-policy.md`）
- 跨域基础：单名（如 `data-model.md`、`template.md`）
- Infra 模块：`infra-<topic>.md`
- Codegen 平台：`codegen-<topic>.md`

新增 spec 必须从 `template.md` 起手。

## 索引

| Spec | 关注点 | 实施状态 |
|---|---|---|
| **跨域基础** | | |
| `data-model.md` | 21 张表的 DDL 与索引，唯一权威源 | MVP 必须实现 |
| `template.md` | 新建 spec 的模板 | — |
| **业务规格** | | |
| `domain-gov-policy.md` | 政府产业政策业务规格（采集范围 / 6 类数据 / 36 字段 / 验收） | MVP 实施 |
| **Infra · 采集运行时** | | |
| `infra-fetch-policy.md` | 限流 / 重试 / robots / 反爬识别 / 紧急止损 / warm-up | MVP 必须实现 |
| `infra-resilience.md` | 增量抓取 / checkpoint / 异常分级 / 心跳 / 版本巡检 | MVP 暂缓（TD-010~012） |
| **Infra · 部署与协调** | | |
| `infra-deployment.md` | 主从分布 / 自建分发 / SKIP LOCKED / master lease | MVP 单进程；扩展期升级（TD-015） |
| **Infra · 可观测与可视化** | | |
| `infra-observability.md` | 采集负载 / 存储 / AI 成本指标 + cron 告警 + LiteLLM | MVP 暂缓（TD-013） |
| `webui.md` | Webui · 任务后台 + 采集监控 + 结果浏览（FastAPI `/api/*` + React + Ant Design ProComponents） · AuthBackend 抽象 | React 重写实施（OAuth 暂缓 TD-018） |
| **Infra · 通用爬虫引擎** | | |
| `infra-crawl-engine.md` | CrawlEngine 契约 / BFS-DFS routing order / 4 scope mode / 递归发现 / 翻页 helper | MVP 已实现核心 |
| **Codegen 平台** | | |
| `codegen-output-contract.md` | Adapter 内部架构 / 默认 sink / harness 门槛 / prompt 框架 | M3.5 实施 |
| `codegen-auto-merge.md` | 跳过人审的安全网：tier 分级 / 渐进 canary / 自动回滚 / 审计 | M3.5 实施 |

## 跨 spec 关系（速查）

```
domain-gov-policy ──→ data-model（业务表）
                   └→ codegen-output-contract（业务侧 harness_rules / golden / prompt）

codegen-output-contract ─→ codegen-auto-merge（tier 与 canary 触发条件）
                         ├→ data-model（crawl_raw 等）
                         └→ infra-crawl-engine（adapter 协议被引擎调度）

infra-crawl-engine ──→ infra-{fetch-policy,resilience}（HTTP / robots / 增量）
                    ├→ data-model（url_record / fetch_record / crawl_raw）
                    └→ codegen-output-contract（消费 ParseListResult / ParseDetailResult）

codegen-auto-merge ──→ infra-fetch-policy（warm-up 联动）
                    └→ infra-observability（审计 webhook 通道）

infra-fetch-policy ←→ infra-resilience（互补：礼貌 vs 高效）
infra-resilience  ──→ data-model（task_checkpoint / crawl_dlq / url_record）
infra-deployment  ──→ data-model（master_lease / 4 张 task 表）
infra-observability ──→ data-model（metric_snapshot / alert_history）

webui ──→ data-model（crawl_task 写、url_record / fetch_record / crawl_raw 读、webui_audit）
       ├→ infra-adapter-registry（/adapters 列表）
       └→ infra-observability（监控视图依赖 metric_snapshot；TD-013 之前用既有 4 表降级）
```

> 修改 spec 必须同 PR 追加 `## 修订历史` 一行并 bump frontmatter rev。详
> 见 `AGENTS.md` 的 `Spec Versioning` 节。
