# infra/

跨业务域复用的**纯技术能力**。**不得**包含任何业务规则（如政策行业分
类、字段语义判断、政府发文层级判定）。这些都属于 `domains/<context>/`。

判定 "属于 infra 还是 domain" 的简单准则：

- 这段逻辑能被另一个业务域（如 `exchange_policy`）原样复用吗？
  - 是 → `infra/`
  - 否 → `domains/<context>/`

## 执行面模块（MVP 阶段建设）

| 模块 | 状态 | 职责 | 建设任务 |
|---|---|---|---|
| `storage/` | 待建 | `MetadataStore`/`BlobStore` 协议；SQLite/PolarDB/LocalFS/OSS 实现；`STORAGE_PROFILE` 切换；OSS 用量监控 | T-20260427-102、T-20260428-302 |
| `http/` | 待建 | HTTP 客户端、UA、cookie jar、Retry-After/退避、host 令牌桶、反爬识别、条件请求（ETag/Last-Modified） | T-20260427-103、T-20260427-115 |
| `robots/` | 待建 | RFC 9309 实现、24h 缓存、5xx → complete disallow | T-20260427-104 |
| `frontier/` | 待建 | 单进程两级队列、三类令牌、host cooldown / disable | T-20260427-105 |
| `checkpoint/` | **暂缓**（TD-010） | 任务级 checkpoint、pause/resume/restart API、幂等键守护 | — |
| `ai/` | 待建 | LiteLLM gateway 接入、prompt 模板装载器、schema 校验 | T-20260427-111 |
| `observability/` | **暂缓**（TD-013） | recorder + metric_snapshot 表、cron 告警 + IM webhook | — |

## 部署与可视化模块（已设计，MVP 暂缓）

| 模块 | 状态 | 职责 | 关联 |
|---|---|---|---|
| `dispatch/` | **暂缓**（TD-015） | 主从分布的自建分发系统：master 派发 + slave 拉取 + lease 管理；HTTP+JSON 协议；不用 Airflow/Celery | `infra-deployment.md` |
| `visualization/` | **暂缓**（TD-014） | FastAPI + Jinja2 + Chart.js 轻量看板；可嵌入 master 进程或独立部署 | `infra-visualization.md` |

## Codegen 平台模块（M3.5 阶段建设）

| 模块 | 状态 | 职责 | 建设任务 |
|---|---|---|---|
| `agent/` | 待建 | `CodingAgentBackend` 协议；默认 `OpenCodeBackend`；备选 `ClaudeCodeBackend` / `MockBackend` | T-20260428-201 |
| `sandbox/` | 待建 | git worktree 隔离 + 文件系统白名单 + 网络白名单 | T-20260428-202 |
| `harness/` | 待建 | 验证 harness 框架；业务规则由 domain 注入 | T-20260428-203 |
| `codegen/` | 待建 | codegen worker 主循环 + `TaskSource` 协议（消费端） | T-20260428-204、205 |
| `adapter_registry/` | 待建 | 入口点扫描注册 `(host, data_kind, version)` | T-20260428-206 |
| `scheduler/` | 待建 | 定时调度 + 金丝雀池（阈值参数化，待定） | T-20260428-207 |
| `version_guard/` | **暂缓**（TD-012） | 站点版本巡检：黄金 fixture 回放 + 解析失败率监测 + 自动 fix-task | — |

> Task API / Task Store 不在本仓库——属外部独立项目。本仓库只建消费端。

## 共同遵守的契约

- `docs/prod-spec/infra-fetch-policy.md` —— 限流/重试/反爬识别/紧急止损
- `docs/prod-spec/infra-resilience.md` —— 增量抓取/checkpoint/版本巡检/异常分级
- `docs/prod-spec/observability.md` —— 三类核心指标与告警阈值（零自建后台版）
- `docs/prod-spec/infra-visualization.md` —— 自建轻量看板形态
- `docs/prod-spec/infra-deployment.md` —— 主从分布部署 + 自建分发协议
- `docs/prod-spec/codegen-output-contract.md` —— Adapter 内部架构 + 默认 sink schema + harness 门槛 + prompt 框架
- `docs/prod-spec/auto-merge-policy.md` —— 跳过人审的安全网（tier 划分 + 加压门槛 + 渐进 canary + 自动回滚 + 审计）
- `docs/prod-spec/data-model.md` —— 所有表 DDL 与索引的唯一权威源

## 反向依赖禁令

`infra/*` 不得 import `domains/*`。CI 应在后续阶段加 import-linter 守护。
