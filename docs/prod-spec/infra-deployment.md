# Infra 部署与分发 · 主从分布 + 自建分发

> **版本**：rev 3 · **最近修订**：2026-04-28 · **状态**：active
> **实施状态**：本 spec 是已通过的设计契约。MVP plan 暂以单进程跑通；进入扩展期（≥ M4）后按本 spec 升级到主从（TD-015）。
>
> **关键决策**：**主从分布部署**；**不用** Airflow / Celery / Kafka / Temporal
> 等外部编排平台；**自建轻量分发系统**，写在 `infra/dispatch/`。

## 1. 角色

| 角色 | 职责 | 数量 |
|---|---|---|
| **Master** | Frontier 主队列；任务派发；状态聚合；checkpoint 持久化；版本巡检调度；可选承载 dashboard（visualization）| 1 主 +（可选）1 备 |
| **Slave Worker** | 无状态执行节点：抓取 / 解析 / AI 抽取 / sink；从 master 拉任务，跑完回报 | N 个，弹性扩缩 |
| **Adapter Codegen Worker** | M3.5 引入；与 slave 解耦的特殊节点：从外部 task 项目消费 codegen task，调 OpenCode 写代码 | 1–2 个 |

Master 本身不做 fetch / parse 等耗时操作，避免热点。

## 2. 数据流

```
[外部 Task 项目] ──→ Master ──→ Frontier ──┐
                       ▲                     │
                       │ 状态回报             │ pull
                       │                     ▼
                  Slave Worker ←──── HTTP /next
                       │
                       ├── infra/http  抓
                       ├── infra/parse 解析
                       ├── infra/ai    抽取
                       └── infra/storage  写 PolarDB / OSS
                       │
                       └─→ HTTP /report ──→ Master 聚合
```

通信选型：**HTTP / JSON over TCP**（FastAPI master + httpx slave），不用
gRPC、不用消息队列、不用 RPC 框架。

## 3. 任务派发协议

### 3.1 Slave 拉取

```
POST /v1/work/next
{
  "worker_id":   "slave-7",
  "capacity":    8,                  # 一次最多领多少 URL
  "capabilities": ["fetch","parse","extract"],
  "supported_hosts": null            # null=任意；亦可声明亲和性
}

Response:
{
  "lease_id": "lse_01J...",
  "lease_expire_at": "2026-04-28T10:05:00Z",
  "items": [
    { "url": "...", "task_id": "...", "url_fp": "...",
      "host": "...", "adapter": "gov_policy.statecouncil",
      "constraints": { "politeness_rps": 1.0, "robots_strict": true } },
    ...
  ]
}
```

### 3.2 Slave 回报

```
POST /v1/work/report
{
  "lease_id": "lse_01J...",
  "results": [
    { "url_fp": "...", "status": "ok", "raw_blob_uri": "oss://...",
      "fetch_record": {...}, "parse_record": {...}, "extract_record": {...} },
    { "url_fp": "...", "status": "fetch_failed", "error_kind": "tcp_reset" },
    { "url_fp": "...", "status": "anti_bot_detected", "signal": "challenge_page" }
  ]
}
```

### 3.3 Master 行为

- 收到 `report`：按 url_fp 幂等更新 `url_record` / `fetch_record`，把异常结果放 DLQ
- Lease 超时未回报：URL 重新入队，attempts++（仍受 retry_max 约束）
- 反爬命中：触发 `frontier` 中的 host cooldown / disable
- 自动止损（`infra-fetch-policy.md` §7）由 master 进程内执行，不依赖 slave

### 3.4 多实例并发竞争（`SELECT ... FOR UPDATE SKIP LOCKED`）

不论 master 主备 / slave 池 / generator 池 / runner 池，凡涉及"从同一表
中抢一条任务"，统一用 PolarDB（兼容 MySQL）的 `SELECT ... FOR UPDATE SKIP LOCKED`
模式（PostgreSQL 同名语义）。**不**自实现分布式锁，**不**用 Redis。

```sql
BEGIN;
SELECT id, ... FROM tasks
 WHERE status = ?
   AND next_run_at <= NOW()
 ORDER BY priority DESC, next_run_at ASC
 LIMIT 1
 FOR UPDATE SKIP LOCKED;        -- 被别人锁住的行直接跳过

UPDATE tasks SET status='claimed', worker_id=?, claim_at=NOW() WHERE id=?;
COMMIT;
```

行为约定：

- **不阻塞等待**：被锁行直接跳过，poller 看下一条
- **事务结束即释放锁**：进程崩溃 → 锁释放 → 心跳 stale 扫描接管（`infra-resilience.md` §2.5）
- **批量抢占**：单次 poller 循环 N 次抢 N 条，总耗时 ≤ poller 间隔
- **优先级与公平性**：`ORDER BY priority DESC, next_run_at ASC` 必须在 `FOR UPDATE` 前生效

适用场景：generator poller 抢 PENDING / FAILED 任务；runner poller 抢
READY / SCHEDULED 任务；master HA 备 → 主切换；slave 拉取 URL（粒度更细，
基于 frontier 内部队列而非 SQL 表，但同样语义）。

## 4. Master 高可用

MVP（单 master）默认单实例。扩展期按以下方式上 HA：

| 方案 | 说明 | 选用条件 |
|---|---|---|
| **单 master + 进程守护**（默认） | systemd / k8s Deployment replicas=1 | 业务可接受 ≤ 5min 切换 |
| **主备 + Lease** | 主备两实例，争抢 SQL/etcd lease；活的为 active | 业务要求 < 1min 故障转移 |
| ~~多 master 分片~~ | 按 host 一致性哈希分片 | 暂不做，扩到亿级再考虑 |

Lease 走 PolarDB 表 `master_lease`（DDL 权威源 `data-model.md` §4.4.1）。
续约 SQL：

```sql
-- 主：每 10s 续约
INSERT INTO master_lease (name, holder, acquired_at, expire_at)
VALUES ('master', ?, NOW(), DATE_ADD(NOW(), INTERVAL 30 SECOND))
ON DUPLICATE KEY UPDATE
    holder = IF(expire_at < NOW() OR holder = VALUES(holder), VALUES(holder), holder),
    acquired_at = IF(holder = VALUES(holder), VALUES(acquired_at), acquired_at),
    expire_at = IF(holder = VALUES(holder), VALUES(expire_at), expire_at);
```

无需 etcd / Consul / ZooKeeper。配合 §3.4 的 SKIP LOCKED 模式覆盖所有
分布式协调诉求。

## 5. Slave 调度 / 横向扩缩

- 部署：k8s Deployment（无状态）+ HPA 看任务积压量
- HPA 自定义指标：从 `metric_snapshot` 读 `frontier_pending`，超阈值扩；空闲缩
- 优雅退出：Slave 收 SIGTERM → 完成当前 lease 后退出 → master 不再分配
- 无亲和性约束（任何 slave 可处理任何 host），后续可按需加

## 6. 自建分发的 vs 外部平台

| 维度 | 自建（本 spec） | Airflow | Celery | Kafka |
|---|---|---|---|---|
| 部署复杂度 | FastAPI + DB | DAG + Webserver + Scheduler + Executor + DB | broker + worker + result backend | broker cluster + ZK |
| 学习曲线 | 低 | 高 | 中 | 高 |
| 任务粒度 | URL / 任务 | DAG / Task | task | message |
| 主从语义 | 显式建模 | 不天然支持 | 隐式 | 不天然支持 |
| 持久化与回放 | DLQ + 补偿队列 | DAG 重跑 | 需 result_backend | 天然 |
| 监控集成 | 用本仓库 visualization | UI 但要部署 | flower | 需自配 |
| 我们的需求 | URL 级 + host 礼貌性 + adapter 路由 | DAG 不太对路 | task 太通用 | 体量过剩 |

**结论**：URL 级 + host 礼貌性 + adapter 路由 + 反爬识别这些诉求高度业务
化，套外部平台反而增加抽象层；自建薄薄一层 master-slave 分发刚好。

## 7. `infra/dispatch/` 模块

| 子模块 | 职责 |
|---|---|
| `infra/dispatch/master.py` | FastAPI 路由：`/v1/work/next`、`/v1/work/report`、`/v1/admin/...` |
| `infra/dispatch/slave.py` | 长循环：pull → execute → report → sleep；带优雅退出 |
| `infra/dispatch/lease.py` | URL lease 管理（DB 行）；超时回收 |
| `infra/dispatch/master_lease.py` | 主备 master 的 SQL lease（HA 时启用） |
| `infra/dispatch/protocol.py` | Pydantic 模型（拉/回报 payload）；版本协商 `/v1/info` |

通信契约 `/v1/info` 提供版本：master 与 slave 不匹配时拒绝注册并告警。

## 8. 与其他 spec 的接口

- Frontier 仍由 `infra/frontier/` 实现；master 持有它的实例；slave 不直接访问
- HTTP / robots / parse / dedup / extract / sink：slave 内调，master 不参与
- Checkpoint / 版本巡检（resilience）：master 侧守护
- Visualization：可嵌入 master 进程同 ASGI 应用，或独立部署
- Codegen worker：与 slave 共存于 k8s 但**走完全独立的命名空间与白名单**（`sandbox` 隔离，不复用 slave 的运行身份）

## 9. 默认值

```
master_listen_addr           = 0.0.0.0:8080
slave_pull_capacity          = 8
slave_pull_idle_sleep_sec    = 5
url_lease_seconds            = 300
url_lease_renew_threshold    = 0.5      # 还剩 50% 时续约
master_lease_ttl_sec         = 30
master_lease_renew_interval  = 10
hpa_target_pending_per_slave = 200
```

## 10. 验收点

- TD-015 立项后实现；MVP 单进程不走 master-slave
- 切换验收：相同 100 条政策任务，单进程时间 vs 1 master + 4 slaves 时间，slave 模式 ≥ 2.5x 加速
- 主备 HA：kill master 后，备 master 30s 内接管，url 不丢

## 11. 不在 v1 范围

- 多 master 分片 / 一致性哈希
- 跨数据中心
- 工作窃取（work stealing）；slave 失败由 lease 超时回收即可
- 复杂 DAG 编排（用不上）

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 3 | 2026-04-28 | §4 master_lease 表 DDL 移交 `data-model.md` §4.4.1 为权威源 | data-model.md 创建 |
| rev 2 | 2026-04-28 | 新增 §3.4 多实例并发竞争（`SELECT ... FOR UPDATE SKIP LOCKED`），明确 generator/runner/HA 切换均走该模式；§4 master_lease 表给出具体 SQL | 借鉴上一版 implementation-plan |
| rev 1 | 2026-04-28 | 初稿 | — |
