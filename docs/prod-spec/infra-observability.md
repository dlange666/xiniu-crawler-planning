# Observability · 零自建后台版
> **版本**：rev 1 · **最近修订**：2026-04-28 · **状态**：active


> **实施状态**：本 spec 是已通过的设计契约。MVP plan 暂不实现（TD-013，plan
> 移至 `docs/exec-plan/deferred-plan.md`），但 spec 永远是后续编码的权威。
>
> **背景**：当前没有公司级 Prometheus / VictoriaMetrics / 云 Prometheus
> 拉取端。本 spec 给出**完全不引入新基础设施**的最小可观测方案：
> 指标存在与业务同一个 DB，告警靠 cron + SQL + IM webhook。
> 等后续公司基础设施就位（TD-005），把 recorder 替换成 prometheus-client
> 即可，业务代码不变。

## 1. 范围

| 关注点 | 关键问题 |
|---|---|
| 采集负载（P3） | frontier 是否积压？host 是否被限流？任务 SLA 撑得住吗？ |
| 存储容量（P4） | OSS 增长率？保留期内对象数？月度存储成本预估？ |
| AI 成本（P8） | 单任务 token 用量？fallback ratio？月度推理成本？ |

## 2. 实现栈（零自建服务）

```
业务代码                  ← 调 recorder.incr/observe/set
   │
   ▼
infra/observability/      ← 进程内聚合（counter/gauge/histogram-bucket）
   │
   ├── 每 60s flush ─→  metric_snapshot 表（PolarDB / SQLite）
   │
   ├── ad-hoc 查询  ─→  scripts/observe_dump.py
   │
   └── 定时扫描     ─→  scripts/observe_check.py（cron 每 5min）
                              │
                              ▼ 命中阈值
                          IM webhook（钉钉 / 飞书 / 企微）
```

| 组件 | 选型 | 自建？ |
|---|---|---|
| 指标记录器 | `infra/observability/recorder.py`（接口与 prometheus-client 兼容） | 否，仅库 |
| 指标存储 | DB 表 `metric_snapshot`（同业务 DB） | 否，复用 |
| 拉取/采集进程 | 不需要 | — |
| 告警 | cron + SQL + webhook | 否，复用现有 cron |
| AI 成本 | LiteLLM gateway（公司既有外部服务） | 否，外部已有 |
| OSS 用量 | 阿里云 OSS API 轮询 | 否，外部已有 |

**关键设计**：业务调用方式与 prometheus-client 一致。后续切真 Prometheus
只改 `recorder.py` 一个文件。

## 3. 表 schema

```
metric_snapshot {
  ts                  ts            -- 60s 一行
  metric_name         str
  labels_json         json          -- {"task":"...","host":"...","status":"200"}
  value               float
  kind                enum          -- counter | gauge | histogram_bucket
}
索引：(ts), (metric_name, ts)
保留期：90d（合规阶段再扩到 180d，见 TD-009）
```

写入策略：
- 进程内每 60s flush 一次当前所有指标
- counter 写"自上次 flush 的增量"（便于聚合）
- gauge 写当前值
- histogram 拆成多行（每 bucket 一行）

## 4. 采集负载指标（P3）

| 指标 | 类型 | 标签 | 含义 |
|---|---|---|---|
| `crawler_fetch_total` | counter | task, host, status_code | 累计抓取请求数 |
| `crawler_fetch_latency_ms` | histogram | task, host | 抓取耗时（5/50/95/99 分位 + 桶） |
| `crawler_frontier_pending` | gauge | task | 待抓 URL 数 |
| `crawler_frontier_active_hosts` | gauge | task | 活跃 host 数 |
| `crawler_frontier_cooldown_hosts` | gauge | task | cooldown host 数 |
| `crawler_anti_bot_events_total` | counter | host, signal | 反爬事件累计 |
| `crawler_dlq_size` | gauge | task, layer | DLQ 长度（resilience §4.2） |
| `crawler_parse_fail_ratio` | gauge | host | 滚动 1h 解析失败率 |

## 5. 存储容量指标（P4）

通过定时脚本 `scripts/observe_oss_usage.py` 每小时调阿里云 OSS API：

| 指标 | 类型 | 标签 | 含义 |
|---|---|---|---|
| `crawler_oss_bytes_total` | gauge | bucket, prefix | 当前对象总字节 |
| `crawler_oss_object_count` | gauge | bucket, prefix | 当前对象数 |
| `crawler_oss_daily_growth_bytes` | gauge | bucket | 24h 新增字节 |
| `crawler_oss_estimated_monthly_cost_cny` | gauge | bucket | 按公开价 + 当前用量估算 |

OSS prefix 规范：`raw/<yyyy>/<mm>/<dd>/<task_id>/<url_fp>.<ext>`，便于按时间/任务统计。

## 6. AI 成本指标（P8，通过 LiteLLM）

`infra/ai/budget.py` 守护每 10min 调 LiteLLM `/spend/get`，把以下指标写入
`metric_snapshot`：

| 指标 | 类型 | 标签 | 含义 |
|---|---|---|---|
| `crawler_ai_tokens_total` | counter | task, context, model, kind=in/out | 累计 token |
| `crawler_ai_cost_usd_total` | counter | task, context, model | 累计费用 |
| `crawler_ai_call_total` | counter | task, context, model, status | 调用次数（含 cache_hit） |
| `crawler_ai_cache_hit_ratio` | gauge | context, model | 缓存命中率 |
| `crawler_ai_fallback_ratio` | gauge | context | LLM 在主路径占比 |
| `crawler_ai_budget_remaining_usd` | gauge | scope | LiteLLM 后台预算剩余 |

调用 LiteLLM 时透传 `x-litellm-tags: task=...,context=...`，便于按维度聚合。

预算守门（同前）：剩余 < 20% 告警；< 5% 暂停非紧急抽取；= 0 由 LiteLLM
gateway 直接拒绝。

## 7. 告警（cron + SQL + webhook）

`scripts/observe_check.py` 每 5 分钟由 cron 触发，跑下列 SQL 检测阈值；
命中即 POST 到 `OBSERVE_WEBHOOK_URL`（钉钉/飞书/企微 webhook）。

| 告警 | 检测 SQL（示意） | 触发动作 |
|---|---|---|
| Frontier 持续积压 | 最近 30min `frontier_pending` 单调增 | webhook 警告 |
| Host 高 4xx/5xx 比例 | 10min 窗口 ≥ 50% | webhook + 自动暂停 host 1h（fetch-policy §7） |
| 反爬事件激增 | 单 host 24h ≥ 3 | webhook + host disabled + 开 fix-task |
| OSS 日增长率 | 7d 日均 > 历史 P95 + 50% | webhook |
| OSS 月成本预估 | 当月预估 > 预算 80% | webhook |
| AI 月成本 | 当月已用 > 预算 80% | webhook |
| AI fallback ratio 异常 | 单 context 24h > 历史 P95 + 10pp | webhook |
| Adapter 解析失败率突增 | 单 host > 历史 P95 + 20pp | webhook + 触发版本巡检（resilience §3.2） |

webhook payload 格式：

```json
{ "alert": "host_4xx_5xx_high", "labels": {...}, "value": 0.62, "ts": "...", "summary": "..." }
```

**所有"自动暂停 host"等动作**仍由进程内的 frontier/anti-bot 触发，不依赖
告警链路；告警链路只负责通知。这样 webhook 故障不会丢失止损。

## 8. 业务域接口

业务域可在 `harness_rules.py` 注入：
- 业务侧自定义指标（如政策维度字段命中率）
- 业务侧告警 SQL 与阈值（仅可收紧）

## 9. 验收点

- recorder + snapshot flush：T-20260428-301
- OSS 用量脚本：T-20260428-302
- LiteLLM 成本：T-20260428-303
- 告警脚本与 webhook：T-20260428-304
- 24h 端到端：T-20260428-305

## 10. 不在 v1 范围

- Prometheus / VictoriaMetrics / Grafana / Alertmanager 完整链路（TD-005 提升后做，仅替换 recorder）
- OTel Trace（M5）
- 日志聚合 Loki/ELK（M5）
- 多实例聚合（单 worker 时不需要）

## 11. 升级到完整 Prometheus 体系的路径

当公司有了 Prometheus 拉取端（任一形式：自建 / VictoriaMetrics / 阿里云
ARMS）时，升级路径：

1. 在 `infra/observability/recorder.py` 增加 `PrometheusBackend`，与现有
   `DBSnapshotBackend` 并存
2. 通过环境变量 `OBSERVE_BACKEND=db|prom|both` 切换
3. 进程暴露 `/metrics`，运维加 scrape config
4. 渐进迁移告警从 cron+SQL 切到 PrometheusRule
5. `metric_snapshot` 表保留 90d 后退役

业务代码完全不动。

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 1 | 2026-04-28 | 初稿 | — |
