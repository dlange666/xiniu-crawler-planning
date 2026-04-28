# Infra 韧性与增量抓取

> **版本**：rev 2 · **最近修订**：2026-04-28 · **状态**：active
> **实施状态**：本 spec 是已通过的设计契约。MVP plan 暂不实现（TD-010 / 011 / 012），但 spec 永远是后续编码的权威。

> 适用：`infra/http/`、`infra/checkpoint/`、`infra/frontier/`、`infra/version_guard/`
> 共同遵守的契约。覆盖四件事：
> 1. **增量抓取**（条件请求 + 内容指纹）
> 2. **Checkpoint 与续抓**（任务可中断、可恢复）
> 3. **站点版本变更检测**（adapter 衰老的早期信号）
> 4. **心跳与卡死恢复**（worker 异常退出后自动复位）
>
> 与 `docs/prod-spec/infra-fetch-policy.md` 互补：fetch-policy 管"礼貌
> 与防绕过"，本 spec 管"高效与不丢任务"。

## 1. 增量抓取

### 1.1 条件请求（RFC 7232）

每个 URL 在 `url_record` 持久化以下字段：

| 字段 | 来源 | 用途 |
|---|---|---|
| `etag` | 上次响应 `ETag` | 下次发 `If-None-Match` |
| `last_modified` | 上次响应 `Last-Modified` | 下次发 `If-Modified-Since` |
| `content_sha256` | 上次正文摘要 | 304 失效时正文摘要兜底 |
| `last_fetched_at` | ts | 触发刷新策略 |

### 1.2 处理矩阵

| 服务端响应 | 行为 |
|---|---|
| 304 Not Modified | 复用旧 raw blob 与已抽取的 JSON；只更新 `last_fetched_at`；不消耗 AI 配额 |
| 200 + 新 ETag/Last-Modified | 更新 validators，下游正常解析→去重 |
| 200 + 同 `content_sha256` | 进解析层去重（已是同一指纹） |
| 200 + ETag 不一致但内容 sha256 一致 | 仅更新 ETag，不重新跑 AI 抽取（节省成本） |

### 1.3 刷新调度

- 首次抓取永远走全量。
- 增量阶段：seed 配置 `refresh_strategy: validator | hash | always`。默认 `validator`（条件请求）。
- 高频列表页：单独 `list_refresh_interval`（默认 1h）。
- 详情页：默认 30d 复刷一次条件请求；命中 304 不做事。

## 2. Checkpoint 与续抓

### 2.1 任务粒度

每个 task 在 `task_checkpoint` 表持久化：

```
task_checkpoint {
  task_id              uuid
  cursor               json     # 列表页分页位、外部源游标
  frontier_snapshot    json     # 待抓 URL 摘要（gz 后 ≤ 1 MB；超出存 OSS）
  metrics              json     # discovered/fetched/parsed/extracted/failed 计数
  last_committed_at    ts
  schema_version       int
}
```

### 2.2 写入频率

| 触发 | 行为 |
|---|---|
| 每 N 页（默认 100） | 写一次 checkpoint |
| 每 M 秒（默认 60） | 写一次 checkpoint |
| 优雅退出（SIGTERM） | 立即 flush + 关 frontier |
| 异常退出 | 下次启动从最近 checkpoint 恢复 |

### 2.3 续抓 API

| API | 行为 |
|---|---|
| `pause_task(task_id)` | 设 `task.status='paused'`；当前 in-flight URL 完成后 worker 停下；写 checkpoint |
| `resume_task(task_id)` | 读最近 checkpoint；frontier 重新装载；继续派发 |
| `restart_task(task_id, from_cursor=null)` | 清 checkpoint + url_record（按 task_id 过滤），重新跑 |

### 2.4 幂等写入保障

- `url_record` 的写入键：`(task_id, url_fp)`，重复写不创建副本。
- `fetch_record` 主键：`(task_id, url_fp, attempt)`；attempt 单调递增。
- `policy_doc` 主键：`(task_id, content_sha256)`；同 task 内同正文哈希仅留一份。

### 2.5 心跳与卡死恢复

外部 task 项目的 `tasks` 表持久化 `heartbeat_at`；本仓库 worker 仅负责更新
心跳与按 stale 判定恢复，不持有 tasks 表本身。

| 触发 | 间隔 | 动作 |
|---|---|---|
| Generator（codegen worker）在生成/修复 | 5min | 调外部 task API 更新 `heartbeat_at` |
| Runner（执行 worker）在跑任务 | 5min | 同上 |

Stale 扫描（任一 worker 启动时执行）：

| 状态 | 阈值（无心跳） | 重置动作 |
|---|---|---|
| GENERATING | 60min | → PENDING（清 worker 占位，让其它 generator 抢 lock） |
| RUNNING | 30min | → SCHEDULED，并把 `next_run_at = now()`（让 runner 立即重抓） |

阈值通过环境变量参数化：

```
HEARTBEAT_INTERVAL_SECONDS              = 300
STALE_GENERATING_THRESHOLD_MINUTES      = 60
STALE_RUNNING_THRESHOLD_MINUTES         = 30
```

> 长任务（如全量首抓 24h+）需保证 worker 持续打心跳，不会被误判 stale。
> 心跳更新失败 ≥ 3 次 → 主动退出当前进程，让上游 stale 扫描接管。

## 3. 站点版本变更检测

### 3.1 adapter schema_version 显式声明

每个 `domains/<context>/adapters/<host>.py` 顶部声明：

```python
ADAPTER_META = {
    "host": "www.ndrc.gov.cn",
    "schema_version": 3,           # 站点 DOM 结构变化时手动 bump
    "list_url_pattern": "...",
    "detail_url_pattern": "...",
    "last_verified_at": "2026-04-15",
}
```

### 3.2 巡检机制（`infra/version_guard/`）

实现形态：**命令行脚本 + 外部 cron / Kubernetes CronJob 触发**，无守护进
程。每次执行读 metric_snapshot 表与 golden fixture，命中阈值即写入告警通
道（observability §7 webhook）。

| 巡检 | 触发 | 动作 |
|---|---|---|
| **黄金 fixture 回放** | cron 每日 03:00 | 用本 host 的 `domains/<context>/golden/<host>/*.html` 跑解析；输出与期望 JSON 不等 → webhook + 自动开 fix-task（`task_type=update`） |
| **解析失败率突增** | cron 每 5min | 单 host 滚动 1h 解析失败率 > 历史 P95 + 20pp → webhook |
| **关键字段缺失率突增** | cron 每 1h | 标题/发文字号/发布日期任一缺失率 > 历史 P95 + 10pp → webhook |
| **日活页面数突降** | cron 每日 04:00 | 日新增页面数 < 历史 P5 → webhook（可能列表页改版或反爬升级） |

### 3.3 fix-task 自动开单

巡检命中 → 调外部 task 项目接口创建 `task_type=update` 任务，spec 中带：
- `site_url` = 触发 host
- `scope_description` = "解析失败：<原因摘要>"
- `previous_adapter` = 当前 adapter 路径（agent 据此 diff 修复）
- `failing_samples` = 最近 5 个失败 URL 的快照路径

Adapter 在 fix-task 合入前进入 `degraded`：抓取继续但**不**写正式 `policy_doc`，原始页仍然落盘。

## 4. 异常分级与 DLQ

### 4.1 异常分类

| 层级 | 例子 | 默认处理 |
|---|---|---|
| 网络 | 超时、TLS、DNS、连接重置 | 退避重试（fetch-policy §3） |
| HTTP 5xx | 502/503/504 | 退避重试；同 host 累计 → 紧急止损 |
| HTTP 4xx 非 429 | 401/403/404/410 | 不重试；4xx 进反爬识别（fetch-policy §5），404/410 进 DLQ |
| 解析 | DOM 选择器空、字段缺失 | 不重试；进 DLQ；触发版本巡检 §3.2 |
| 抽取 | LLM 超时、JSON schema 不合 | 重试 ≤ 2 次；超额进 DLQ |
| Sink | OSS PUT 失败、DB 连接 | 退避重试；超额进补偿队列 |

### 4.2 DLQ（Dead Letter Queue）

- 表 `crawl_dlq`：`(task_id, url_fp, layer, error_kind, error_detail, last_attempt_at, attempts)`
- 不删除，只追加。
- 提供查询 API：`list_dlq(task_id, layer?)`；提供 replay API：`replay_dlq(task_id, ids)` 把条目重新入 frontier。
- DLQ 长度纳入观测指标（`docs/prod-spec/infra-observability.md`）。

### 4.3 补偿队列（sink 故障）

- 与 DLQ 区分：补偿队列存"已完成解析但写库失败"的项，正文已在 OSS 落盘。
- 后台守护进程定期重试 sink；最终一致。

## 5. 默认值汇总

```
checkpoint_pages_interval      = 100
checkpoint_seconds_interval    = 60
url_validator_retention_days   = 365  # ETag/Last-Modified 持久化年限
detail_refresh_interval_days   = 30
list_refresh_interval_sec      = 3600
extract_retry_max              = 2
sink_retry_max                 = 5
golden_fixture_check_cron      = "0 3 * * *"   # 每日 03:00
parse_fail_alert_threshold_pp  = 20            # 高于历史 P95 多少个百分点
adapter_disable_threshold      = 5             # 与 fetch-policy 一致
```

## 6. 业务域接口

业务域只能：
- 在 `seeds/<host>.yaml` 配 `refresh_strategy`、`detail_refresh_interval_days`
- 在 adapter 顶部声明 `ADAPTER_META.schema_version`
- 在 `golden/<host>/` 维护快照

业务域**不得**：
- 跳过 checkpoint（任何长任务必须 checkpoint）
- 自定义 DLQ 表
- 私自捕获 infra 抛出的异常并吞掉（必须落到 DLQ 或重抛）

## 7. 验收点

- 增量：T-20260427-115（条件请求 + 304 复用）
- Checkpoint：T-20260427-116（pause/resume + 异常恢复）
- 异常分级：T-20260427-117（DLQ + 补偿队列）
- 鲁棒性 fixture：T-20260427-118（7 个场景，研究报告 §6 删 #7 渲染、#9 删除）
- 版本巡检：T-20260428-211（M3.5 阶段，依赖 codegen 接口）

## 8. 不在 v1 范围

- 跨进程分布式 checkpoint（单 worker 时不需要；TD-004 提升后再做）
- 自动 schema diff 修复（仅触发 fix-task；agent 修代码）
- ML 检测站点版本变化（v1 仅规则）

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 2 | 2026-04-28 | 新增 §2.5 心跳与卡死恢复（5min 心跳；GENERATING 60min / RUNNING 30min stale 阈值；自动复位规则）；§ 列表加第 4 项 | 借鉴上一版 implementation-plan |
| rev 1 | 2026-04-28 | 初稿 | — |
