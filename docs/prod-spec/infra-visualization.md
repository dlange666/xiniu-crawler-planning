# Infra 可视化 · 自建轻量看板
> **版本**：rev 1 · **最近修订**：2026-04-28 · **状态**：active


> **实施状态**：本 spec 是已通过的设计契约。MVP plan 暂不实现（TD-014）。
>
> **背景**：暂无 Grafana / 其他 BI。需要让 ops/dev 在浏览器看到运行状态，
> 但又不引入新的基础设施服务。本 spec 给出**单进程内嵌 Web 服务 + 服务
> 端渲染** 的最小可视化方案，与 `infra-observability.md` 同源数据
> （`metric_snapshot` 表）。

## 1. 范围

| 关注点 | 关键问题 | 来源数据 |
|---|---|---|
| 任务总览 | 哪些任务在跑？进度多少？ | `crawl_task` + `task_checkpoint` |
| 抓取健康 | frontier 积压？host 状态？反爬事件？ | `metric_snapshot` 采集负载组 |
| 解析与抽取 | 解析失败率？AI 调用？schema 合格率？ | `metric_snapshot` AI 组 + `policy_doc` |
| 存储与成本 | OSS 增长？AI 费用？预算剩余？ | `metric_snapshot` OSS/AI 组 |
| 告警历史 | 最近触发了什么？ | `alert_history` 表 |
| Adapter 健康 | 哪些站点适配器在跑？degraded？ | `adapter_registry` + adapter 维度指标 |

## 2. 实现栈

```
浏览器 ─→ FastAPI（同 crawler 进程或独立进程，二选一）
                │
                ├── 服务端模板（Jinja2）─→ HTML
                ├── /api/* ─→ JSON ─→ Chart.js 客户端绘图
                └── 静态文件 ─→ Chart.js + 极少量 CSS（无前端框架）
                │
                └─→ 读 PolarDB / SQLite（observability + 业务表）
```

| 组件 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | 已是 crawler 默认依赖，不引入新栈 |
| 模板 | Jinja2 | 标准、无依赖 |
| 图表 | Chart.js（CDN 引入或本地静态） | 单文件，零构建 |
| 鉴权 | HTTP Basic（用户名 + 密码哈希） | 内网最简方案 |
| 静态资源 | FastAPI 自带 StaticFiles | 不引入 CDN/Nginx |

**没有**：Vue/React、TS/前端构建、Webpack、单独的 Node 服务、Grafana、Tableau。

## 3. 页面设计

| 路径 | 内容 |
|---|---|
| `/` | 首页：当前活跃任务卡片（进度条、状态、最近 1h 抓取量、当前 AI 成本）；本月 AI 成本汇总；OSS 用量增长趋势 |
| `/tasks` | 任务列表：筛选 status / business_context；分页 |
| `/tasks/<task_id>` | 单任务详情：discovered/fetched/parsed/extracted 四级数据漏斗；时间序列图（按 5min 粒度）；DLQ 数量；checkpoint 时间 |
| `/hosts` | host 列表：active / cooldown / disabled；每 host 24h 抓取量、429/5xx 比例、反爬事件数 |
| `/hosts/<host>` | 单 host 详情：状态机历史、解析失败率历史、关键字段缺失率历史 |
| `/adapters` | 已注册 adapter 列表：(host, data_kind, schema_version, last_verified_at, 状态) |
| `/alerts` | 告警历史：最近 30d 触发列表，点开看 payload |
| `/spend` | LiteLLM 成本视图：按 task / business_context / model 分组；月预算消耗条 |
| `/api/*` | JSON 端点，给 Chart.js 取数 |

## 4. API 端点

| 端点 | 返回 |
|---|---|
| `GET /api/tasks` | 任务列表（分页） |
| `GET /api/tasks/{id}/timeseries?metric=...&from=...&to=...` | 单任务指标时间序列 |
| `GET /api/hosts/{host}/timeseries?metric=...` | 单 host 指标时间序列 |
| `GET /api/spend?scope=...&from=...&to=...` | AI 成本聚合 |
| `GET /api/alerts?from=...&limit=100` | 告警历史 |

返回格式统一：

```json
{ "labels": ["2026-04-28T08:00", ...], "series": [{ "name": "...", "values": [...] }] }
```

## 5. 部署形态

两种均支持：

| 形态 | 说明 | 适用 |
|---|---|---|
| **嵌入 master 进程** | crawler master 进程同时跑 Web 服务（FastAPI 在同一 ASGI 应用） | 最省资源；MVP 形态 |
| **独立部署** | 单独跑 `scripts/run_dashboard.py`，只读 DB | 当流量上来或需要独立扩缩 |

部署形态由环境变量 `DASHBOARD_MODE=embedded|standalone` 切换。

## 6. 安全

- 默认 `127.0.0.1` 监听；公网暴露需走运维显式配置
- HTTP Basic：用户名密码读 `.env`；密码 hash（bcrypt）
- 不做用户体系（仅 1–N 个内网账号；MVP 单账号即可）
- 操作类 API（暂停任务/disable adapter）放 `/api/admin/*`，要单独二次确认

## 7. 性能预算

- 单任务详情页 SQL 查询 ≤ 5 条，总耗时 < 200 ms（指标表已按 ts/metric_name 建索引）
- `metric_snapshot` 表查询走 `(metric_name, ts DESC)` 索引；超 7d 的查询走预聚合视图
- 首页与列表页不允许全表扫描；任何潜在全表扫描通过 `EXPLAIN` 守护

## 8. 与其它 spec 的接口

- 数据来源：`infra-observability.md`（指标）、`infra-resilience.md`（checkpoint）、`domain-gov-policy.md`（业务表）
- 操作 API（暂停 / 重启）调用：`infra/checkpoint/` 提供的 `pause_task` / `resume_task`
- 鉴权配置：与外部 task 项目无关；本仓库自管

## 9. 验收点

- 后续立项（TD-014）；先不入 MVP plan
- 验收建议：跑 24h 任务后，每个页面在 200ms 内打开，关键图表不空，操作 API 端到端可用

## 10. 不在 v1 范围

- 移动端适配（v1 只保证桌面浏览器可用）
- 多用户体系（暂不需要）
- 编辑业务规则的 UI（业务规则通过 PR 改代码）
- 实时推送（首版每页 30s 自动刷新即可）

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 1 | 2026-04-28 | 初稿 | — |
