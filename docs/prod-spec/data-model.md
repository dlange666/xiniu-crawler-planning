# 数据模型 · 表与索引权威标准

> **版本**：rev 5 · **最近修订**：2026-04-29 · **状态**：active
> **实施状态**：本 spec 是**所有表 DDL 的唯一权威来源**。各业务/能力 spec 描述设计动机与字段语义，本 spec 给最终落库的完整 SQL 与索引。

> **写作约定**：
> - PolarDB（生产 / MySQL 兼容）+ SQLite（开发测试）双形态。差异处用 §6 类型映射统一。
> - **尽量不使用 JSON 字段**。仅当字段确属"动态结构 / 一次性写入 / 不参与 SQL 检索"时才用 JSON（见 §1.3）。
> - 数组字段用子表，不用 JSON 数组。
> - 状态字段用 ENUM（SQLite 用 CHECK 约束模拟）。

## 1. 范围与原则

### 1.1 收录范围

本 spec 收录跨业务域 / 跨能力共享的表。**业务专属表**（如 `policy_doc`、
`policy_similar_cluster`）在各业务域 spec 内定义，本 spec 不收录但在 §3
ER 图中标注关联点。

### 1.2 表权属

- **本仓库表**：采集运行时、韧性、协调、反爬、观测、审计 —— 共 13 张。
- **外部 task 项目表**：4 张任务管理表（`crawl_task` / `crawl_task_generation` / `crawl_task_execution` / `crawl_task_run`）+ 3 张子表 + 1 张审计 —— **schema 标准在本仓库（外部项目对齐）**。

### 1.3 何时允许 JSON

| 场景 | 是否 JSON | 例 |
|---|---|---|
| 数组（小、定长、查询模式确定） | ❌ 用子表 | sample_urls → `crawl_task_seed_url` |
| 数组（动态、变长、按 task 整批读） | ✅ 极少数允许 | — |
| 嵌套结构（query-pattern 已知） | ❌ 字段平铺 | scope.mode → `scope_mode` 列 |
| 嵌套结构（adapter 自定义、不参与 SQL） | ✅ | parse_detail 输出 → `crawl_raw.data` |
| 时序点的多维标签 | ✅ | `metric_snapshot.labels_json` |

## 2. 表分类与命名约定

| 类 | 前缀 | 描述 |
|---|---|---|
| 任务管理 | `crawl_task*` | task 全生命周期 |
| 采集运行时 | `url_record` / `fetch_record` / `crawl_raw` / `crawl_run_log` | 抓取过程数据 |
| 韧性 | `task_checkpoint` / `crawl_dlq` | 续抓与异常队列 |
| 协调 | `master_lease` | 分布式协调 |
| 反爬与告警 | `anti_bot_events` / `alert_history` | 安全事件 |
| 观测 | `metric_snapshot` | 指标快照 |

命名：snake_case；表名单数（`crawl_task` 而非 `crawl_tasks`）；统一字段名
（如 `created_at` / `updated_at`）。

## 3. ER 图（关键关联）

```
[外部 task 项目持有的 4 张主表]

crawl_task ──1:1──> crawl_task_generation
          ├─1:1──> crawl_task_execution
          ├─1:N──> crawl_task_run
          ├─1:N──> crawl_task_seed_url
          ├─1:N──> crawl_task_allowlist_host
          ├─1:N──> crawl_task_expected_field
          └─1:N──> crawl_task_audit_event

crawl_task ──1:N──> url_record (本仓库)
url_record ──1:N──> fetch_record
url_record ──1:N──> crawl_raw           ← 业务 sink 入口；之后 N:1 进 policy_doc（业务表）
crawl_task ──1:1──> task_checkpoint
crawl_task ──1:N──> crawl_dlq
crawl_task ──1:N──> crawl_run_log
crawl_task ──1:N──> alert_history
host       ──1:N──> anti_bot_events       (host 为字符串键，非外键表)
master_lease  独立表
metric_snapshot 独立表（标签维度多）
```

## 4. 完整 DDL

> 以下 DDL 为 PolarDB（MySQL 兼容）形式。SQLite 差异见 §6。

### 4.1 任务管理（外部 task 项目实现，本仓库定标准）

#### 4.1.1 `crawl_task` —— 用户提交的任务定义

```sql
CREATE TABLE crawl_task (
    task_id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    business_context     VARCHAR(50) NOT NULL COMMENT 'gov_policy / exchange_policy / ...',
    task_type            ENUM('create','update','extend') NOT NULL,
    site_url             VARCHAR(2048) NOT NULL,
    host                 VARCHAR(255) NOT NULL COMMENT '从 site_url 解析的 host',
    data_kind            VARCHAR(50) NOT NULL COMMENT 'policy / news / regulation / ...',
    scope_description    TEXT NULL,

    -- 结构化作用域（平铺）
    scope_mode           ENUM('same_origin','same_etld_plus_one','url_pattern','allowlist') NOT NULL DEFAULT 'same_origin',
    scope_url_pattern    VARCHAR(2048) NULL,
    scope_follow_canonical  TINYINT(1) NOT NULL DEFAULT 1,
    scope_follow_pagination TINYINT(1) NOT NULL DEFAULT 1,

    -- 采集模式（平铺）
    crawl_mode           ENUM('full','incremental') NOT NULL DEFAULT 'full',
    crawl_until          DATE NULL,
    full_crawl_cron      VARCHAR(50) NULL,

    -- 约束（平铺）
    max_pages_per_run    INT UNSIGNED NULL,
    run_frequency        VARCHAR(50) NOT NULL DEFAULT 'once' COMMENT 'once / daily / hourly / cron expr',
    schedule_time        VARCHAR(10) NULL COMMENT 'daily 用：HH:MM',
    schedule_minute      TINYINT NULL COMMENT 'hourly 用：第几分钟',
    robots_strict        TINYINT(1) NOT NULL DEFAULT 1,
    politeness_rps       DECIMAL(6,3) NOT NULL DEFAULT 1.000,

    -- 合规预留（C7，TD-009）
    purpose              VARCHAR(500) NULL,
    legal_basis          VARCHAR(500) NULL,
    responsible_party    VARCHAR(100) NULL,

    -- 通用
    priority             TINYINT NOT NULL DEFAULT 5 COMMENT '0 最高，9 最低',
    created_by           VARCHAR(100) NULL,
    created_at           DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at           DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    INDEX idx_context_kind (business_context, data_kind),
    INDEX idx_host (host),
    INDEX idx_created (created_at DESC)
);
```

#### 4.1.2 `crawl_task_generation` —— Codegen 过程状态

```sql
CREATE TABLE crawl_task_generation (
    task_id          BIGINT UNSIGNED PRIMARY KEY,
    status           ENUM('pending','claimed','drafting','sandbox_test','pr_open','merged','failed') NOT NULL DEFAULT 'pending',
    tier             ENUM('tier1','tier2','tier3') NULL COMMENT 'auto-merge-policy §2',
    branch           VARCHAR(255) NULL,
    worktree_path    VARCHAR(512) NULL,
    pr_url           VARCHAR(512) NULL,
    sandbox_run_id   VARCHAR(50) NULL,
    backend          VARCHAR(50) NULL COMMENT 'opencode / claude_code / mock',
    backend_version  VARCHAR(50) NULL,
    attempts         INT UNSIGNED NOT NULL DEFAULT 0,
    last_error       TEXT NULL,
    worker_id        VARCHAR(100) NULL,
    claim_at         DATETIME(3) NULL,
    heartbeat_at     DATETIME(3) NULL,
    started_at       DATETIME(3) NULL,
    finished_at      DATETIME(3) NULL,
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE,
    INDEX idx_status_claim (status, claim_at),
    INDEX idx_stale_heartbeat (status, heartbeat_at)
);
```

#### 4.1.3 `crawl_task_execution` —— 执行状态（高频更新）

```sql
CREATE TABLE crawl_task_execution (
    task_id                BIGINT UNSIGNED PRIMARY KEY,
    status                 ENUM(
                              'scheduled','running',
                              'canary_stage_0','canary_stage_1','canary_stage_2','canary_stage_3',
                              'completed','failed','disabled','rolled_back'
                            ) NOT NULL DEFAULT 'scheduled',
    adapter_host           VARCHAR(255) NULL COMMENT '关联 domains/<ctx>/<source>/<source>_adapter.py',
    adapter_schema_version INT UNSIGNED NULL,
    next_run_at            DATETIME(3) NULL,
    last_run_at            DATETIME(3) NULL,
    last_run_id            VARCHAR(50) NULL,
    last_run_status        VARCHAR(20) NULL,
    last_error_kind        VARCHAR(50) NULL COMMENT 'source_entry_unusable / anti_bot / scope_mismatch / render_required / adapter_bug / audit_gate_failed / infra_error',
    last_error_detail      TEXT NULL,
    last_eval_path         VARCHAR(512) NULL COMMENT '关联 docs/eval-test/*.md 或外部 eval URI',
    needs_manual_review    TINYINT(1) NOT NULL DEFAULT 0,
    last_full_crawl_at     DATETIME(3) NULL,
    canary_stage_until     DATETIME(3) NULL,
    run_count              INT UNSIGNED NOT NULL DEFAULT 0,
    consecutive_failures   INT UNSIGNED NOT NULL DEFAULT 0,
    worker_id              VARCHAR(100) NULL,
    claim_at               DATETIME(3) NULL,
    heartbeat_at           DATETIME(3) NULL,
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE,
    INDEX idx_status_next (status, next_run_at),
    INDEX idx_stale_heartbeat (status, heartbeat_at),
    INDEX idx_adapter (adapter_host)
);
```

`status` / `last_run_status` 只描述状态机位置与最终判定，不承载具体失败类型。
失败原因写入 `last_error_kind` / `last_error_detail`，并把可复现证据写到
`last_eval_path`。当失败需要人工改 PRD seed、scope、合规策略或源站审核时，
`needs_manual_review=1`，调度器不得自动重试同一输入。

推荐 `last_error_kind`：

| error_kind | 含义 | 默认动作 |
|---|---|---|
| `source_entry_unusable` | PRD / task 给出的入口不可直接采集，例如入口命中 WAF、入口是无效筛选页、或详情全部被 scope 拒绝 | failed + manual_review，等待修正 seed/scope |
| `anti_bot` | challenge / captcha / WAF / auth 等保护措施命中 | failed 或 disabled；不绕过，人工审核 |
| `scope_mismatch` | 详情或分页落在 scope 外，需调整 `scope_mode` / allowlist / URL pattern | failed + manual_review |
| `render_required` | 静态抓取无法获得目标内容，且需 headless/render 能力 | failed，等待 render 能力或替代 API |
| `adapter_bug` | adapter 选择器、解析规则、分页规则错误 | failed，可进入 fix-task |
| `audit_gate_failed` | live smoke 成功但质量门不通过 | failed，可进入 fix-task |
| `infra_error` | DB、存储、网络基础设施等非源站/adapter 问题 | failed，可按退避重试 |

#### 4.1.4 `crawl_task_run` —— 每次实际运行的历史记录（append-only）

```sql
CREATE TABLE crawl_task_run (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT UNSIGNED NOT NULL,
    run_id          VARCHAR(50) NOT NULL,
    phase           ENUM('generation','execution','canary') NOT NULL,
    attempt         INT UNSIGNED NOT NULL DEFAULT 1,
    status          ENUM('running','completed','failed','rolled_back') NOT NULL DEFAULT 'running',
    crawl_mode      ENUM('full','incremental') NULL COMMENT '本次实际跑的模式',
    items_count     INT UNSIGNED NOT NULL DEFAULT 0,
    duration_ms     INT UNSIGNED NULL,
    exit_code       INT NULL,
    error           TEXT NULL,
    started_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    finished_at     DATETIME(3) NULL,
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE,
    UNIQUE KEY uq_run_id (run_id),
    INDEX idx_task_started (task_id, started_at DESC),
    INDEX idx_phase_status (phase, status)
);
```

#### 4.1.5 子表（数组字段）

```sql
CREATE TABLE crawl_task_seed_url (
    task_id     BIGINT UNSIGNED NOT NULL,
    ord         SMALLINT UNSIGNED NOT NULL COMMENT '顺序',
    url         VARCHAR(2048) NOT NULL,
    PRIMARY KEY (task_id, ord),
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE
);

CREATE TABLE crawl_task_allowlist_host (
    task_id     BIGINT UNSIGNED NOT NULL,
    host        VARCHAR(255) NOT NULL,
    PRIMARY KEY (task_id, host),
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE
);

CREATE TABLE crawl_task_expected_field (
    task_id     BIGINT UNSIGNED NOT NULL,
    field_name  VARCHAR(100) NOT NULL,
    PRIMARY KEY (task_id, field_name),
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE
);
```

#### 4.1.6 `crawl_task_audit_event` —— 自动合并审计（auto-merge-policy §5）

```sql
CREATE TABLE crawl_task_audit_event (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT UNSIGNED NOT NULL,
    event_type      ENUM('auto_merge','canary_promote','rollback','tier3_block','harness_fail') NOT NULL,
    pr_url          VARCHAR(512) NULL,
    harness_report_uri VARCHAR(512) NULL,
    canary_stage    VARCHAR(20) NULL,
    metric_summary  TEXT NULL COMMENT '关键指标摘要：5xx 比例 / 反爬命中数 / 解析失败率',
    error_reason    VARCHAR(500) NULL,
    fix_task_id     BIGINT UNSIGNED NULL,
    created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE,
    INDEX idx_task_created (task_id, created_at DESC),
    INDEX idx_event_type (event_type, created_at DESC)
);
```

### 4.2 采集运行时

#### 4.2.1 `url_record` —— URL 状态机

```sql
CREATE TABLE url_record (
    task_id           BIGINT UNSIGNED NOT NULL,
    url_fp            CHAR(64) NOT NULL COMMENT 'BLAKE3-256 / SHA-256(canonical_url)',
    url               VARCHAR(2048) NOT NULL,
    canonical_url     VARCHAR(2048) NOT NULL,
    host              VARCHAR(255) NOT NULL,
    etld_plus_one     VARCHAR(255) NOT NULL,
    depth             SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    parent_url_fp     CHAR(64) NULL,
    discovery_source  VARCHAR(20) NULL COMMENT 'seed / anchor / sitemap / pagination / canonical / api',
    priority_score    DECIMAL(6,4) NOT NULL DEFAULT 0.5000,
    scope_decision    ENUM('accepted','rejected_scope','rejected_robots','rejected_dedup') NOT NULL DEFAULT 'accepted',
    frontier_state    ENUM('pending','in_flight','done','failed','dlq') NOT NULL DEFAULT 'pending',
    lease_owner       VARCHAR(100) NULL,
    lease_expire_at   DATETIME(3) NULL,
    etag              VARCHAR(255) NULL COMMENT 'If-None-Match 用',
    last_modified     VARCHAR(64) NULL COMMENT 'If-Modified-Since 用',
    last_content_sha256 CHAR(64) NULL,
    last_fetched_at   DATETIME(3) NULL,
    attempts          SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (task_id, url_fp),
    INDEX idx_task_state (task_id, frontier_state),
    INDEX idx_host_priority (host, priority_score DESC),
    INDEX idx_lease (lease_expire_at)
);
```

#### 4.2.2 `fetch_record` —— 每次 HTTP 抓取一行

```sql
CREATE TABLE fetch_record (
    fetch_id        BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT UNSIGNED NOT NULL,
    url_fp          CHAR(64) NOT NULL,
    attempt         SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    status_code     SMALLINT UNSIGNED NULL,
    rendered        TINYINT(1) NOT NULL DEFAULT 0,
    content_type    VARCHAR(100) NULL,
    bytes_received  INT UNSIGNED NULL,
    latency_ms      INT UNSIGNED NULL,
    etag            VARCHAR(255) NULL,
    last_modified   VARCHAR(64) NULL,
    error_kind      VARCHAR(50) NULL COMMENT 'tcp_reset / dns_fail / 429 / 5xx / parse_fail / anti_bot_*',
    error_detail    TEXT NULL,
    fetched_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uq_task_url_attempt (task_id, url_fp, attempt),
    INDEX idx_task_fetched (task_id, fetched_at DESC),
    INDEX idx_status (status_code)
);
```

#### 4.2.3 `crawl_raw` —— 采集原始记录（业务 sink 入口）

```sql
CREATE TABLE crawl_raw (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT UNSIGNED NOT NULL,
    business_context VARCHAR(50) NOT NULL,
    host            VARCHAR(255) NOT NULL,
    url             VARCHAR(2048) NOT NULL,
    canonical_url   VARCHAR(2048) NOT NULL,
    url_hash        CHAR(64) NOT NULL COMMENT 'SHA-256(canonical_url)',
    content_sha256  CHAR(64) NOT NULL COMMENT 'SHA-256(body_text 规范化后)；解析层去重用',
    raw_blob_uri    VARCHAR(512) NOT NULL COMMENT 'OSS 路径（原始 HTML/PDF）',
    data            JSON NOT NULL COMMENT 'parse_detail 输出 + source_metadata（adapter 自定义结构）',
    etag            VARCHAR(255) NULL,
    last_modified   VARCHAR(64) NULL,
    run_id          VARCHAR(50) NULL,
    created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uq_url_hash (url_hash),
    INDEX idx_task (task_id),
    INDEX idx_context_host (business_context, host),
    INDEX idx_content_sha (content_sha256),
    INDEX idx_created (created_at DESC)
);
```

> `data` 是唯一保留 JSON 的字段——adapter 输出结构因 host 而异，平铺到列不可行。

#### 4.2.4 `crawl_run_log` —— 业务运行日志

```sql
CREATE TABLE crawl_run_log (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT UNSIGNED NOT NULL,
    run_id          VARCHAR(50) NOT NULL,
    business_context VARCHAR(50) NOT NULL,
    status          ENUM('running','completed','failed') NOT NULL DEFAULT 'running',
    items_count     INT UNSIGNED NOT NULL DEFAULT 0,
    error           TEXT NULL,
    started_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    finished_at     DATETIME(3) NULL,
    INDEX idx_task (task_id),
    INDEX idx_run_id (run_id),
    INDEX idx_started (started_at DESC)
);
```

### 4.3 韧性

#### 4.3.1 `task_checkpoint` —— 任务级 checkpoint

```sql
CREATE TABLE task_checkpoint (
    task_id              BIGINT UNSIGNED PRIMARY KEY,
    cursor_pages_done    INT UNSIGNED NOT NULL DEFAULT 0,
    cursor_last_url_fp   CHAR(64) NULL,
    cursor_extra         JSON NULL COMMENT 'adapter 自定义游标',

    -- frontier 摘要
    frontier_pending     INT UNSIGNED NOT NULL DEFAULT 0,
    frontier_in_flight   INT UNSIGNED NOT NULL DEFAULT 0,
    frontier_snapshot_uri VARCHAR(512) NULL COMMENT '超 1MB 时落 OSS',

    -- 计数器（平铺，不用 metrics JSON）
    discovered_count     INT UNSIGNED NOT NULL DEFAULT 0,
    fetched_count        INT UNSIGNED NOT NULL DEFAULT 0,
    parsed_count         INT UNSIGNED NOT NULL DEFAULT 0,
    extracted_count      INT UNSIGNED NOT NULL DEFAULT 0,
    failed_count         INT UNSIGNED NOT NULL DEFAULT 0,

    last_committed_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    schema_version       SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    INDEX idx_committed (last_committed_at)
);
```

#### 4.3.2 `crawl_dlq` —— Dead Letter Queue

```sql
CREATE TABLE crawl_dlq (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT UNSIGNED NOT NULL,
    url_fp          CHAR(64) NOT NULL,
    layer           ENUM('network','http','parse','extract','sink') NOT NULL,
    error_kind      VARCHAR(50) NOT NULL,
    error_detail    TEXT NULL,
    last_attempt_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    attempts        SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    replayed        TINYINT(1) NOT NULL DEFAULT 0,
    INDEX idx_task_layer (task_id, layer),
    INDEX idx_url_fp (url_fp)
);
```

### 4.4 协调

#### 4.4.1 `master_lease`

```sql
CREATE TABLE master_lease (
    name        VARCHAR(50) PRIMARY KEY COMMENT 'master / generator-pool / runner-pool',
    holder      VARCHAR(100) NOT NULL,
    acquired_at DATETIME(3) NOT NULL,
    expire_at   DATETIME(3) NOT NULL,
    INDEX idx_expire (expire_at)
);
```

### 4.5 反爬与告警

#### 4.5.1 `anti_bot_events`

```sql
CREATE TABLE anti_bot_events (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host            VARCHAR(255) NOT NULL,
    task_id         BIGINT UNSIGNED NULL,
    url             VARCHAR(2048) NULL,
    signal          VARCHAR(50) NOT NULL COMMENT 'challenge_page / captcha / waf_block / auth_required / rate_limited',
    detail          TEXT NULL,
    action_taken    ENUM('cooldown','disable','manual_review') NOT NULL,
    cooldown_sec    INT UNSIGNED NULL,
    detected_at     DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_host_detected (host, detected_at DESC),
    INDEX idx_task (task_id)
);
```

#### 4.5.2 `alert_history`

```sql
CREATE TABLE alert_history (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    alert_name      VARCHAR(100) NOT NULL COMMENT 'host_4xx_5xx_high / oss_growth / ai_budget_warn / ...',
    severity        ENUM('info','warn','critical') NOT NULL DEFAULT 'warn',
    labels          VARCHAR(500) NULL COMMENT 'host=...&task_id=... 形式',
    metric_value    DECIMAL(18,6) NULL,
    summary         VARCHAR(500) NULL,
    webhook_status  ENUM('sent','failed','skipped') NOT NULL DEFAULT 'sent',
    triggered_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_name_triggered (alert_name, triggered_at DESC),
    INDEX idx_severity (severity, triggered_at DESC)
);
```

### 4.6 观测

#### 4.6.1 `metric_snapshot`

```sql
CREATE TABLE metric_snapshot (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ts              DATETIME(3) NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,
    labels_json     JSON NULL COMMENT '{"task":"...","host":"...","status":"200"}；标签维度多变，唯一保留 JSON 的列',
    value           DECIMAL(18,6) NOT NULL,
    kind            ENUM('counter','gauge','histogram_bucket') NOT NULL,
    INDEX idx_metric_ts (metric_name, ts DESC),
    INDEX idx_ts (ts)
);
-- 按 ts 月度分区（PolarDB），90 天后归档；TD-009 合规阶段扩到 180 天
```

### 4.7 Webui 审计（rev 2 引入）

#### 4.7.1 `webui_audit` —— webui 写操作的细粒度审计日志

```sql
CREATE TABLE webui_audit (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ts           DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    actor        VARCHAR(255) NOT NULL COMMENT '认证用户的 email 或 sub；DevBackend 下取 WEBUI_DEV_USER',
    role         VARCHAR(20)  NOT NULL COMMENT 'viewer / operator / admin（事件发生时的角色）',
    action       VARCHAR(64)  NOT NULL COMMENT 'submit_task / cancel_task / pause_task / disable_adapter / set_host_rps / ...',
    target_type  VARCHAR(32)  NULL COMMENT 'task / adapter / host / null',
    target_id    VARCHAR(255) NULL,
    payload      JSON NULL COMMENT '参数差异（如新建任务的字段、改限速的前后值）',
    ip           VARCHAR(64)  NULL,
    user_agent   VARCHAR(255) NULL,
    request_id   VARCHAR(64)  NULL COMMENT '请求级 trace id，便于关联日志',
    INDEX idx_actor_ts (actor, ts DESC),
    INDEX idx_action_ts (action, ts DESC),
    INDEX idx_target (target_type, target_id)
);
-- 留存 ≥ 180 天（与 TD-009 合规口径对齐）；超期归档到 OSS Parquet
```

**写入规则**（见 `webui.md` §6）：

- `webui/app.py` 注册中间件，所有 `POST/PUT/DELETE/PATCH` 命中后写一行；GET 不写
- `crawl_task.created_by` 在新建任务时同步填 `actor`，方便任务列表直接显示而无需 join
- 审计字段优先存 `email`；OAuth 阶段若 IdP 不返回 email 则退到 `sub`

> 已存在的 `crawl_task_audit_event`（§4.1.7）不替代本表：前者面向 codegen / 执行链路的事件，后者面向 webui UI 操作。两者按 `request_id` 可关联但 schema 独立。

## 5. 索引规范

### 5.1 强制原则

- 所有 `status IN (...)` 扫描走 `(status, <次序字段>)` 联合索引
- 所有时间倒序列表走 `<key>, <ts> DESC` 联合索引
- 外键字段必须带 INDEX
- `UNIQUE KEY` 用于去重：`url_hash` / `url_fp` 联合 / `run_id`
- 不允许全表扫描的查询：CI 在 `EXPLAIN` 输出里检查 `type != ALL`

### 5.2 冷热数据

- `crawl_raw` / `fetch_record` / `metric_snapshot` 按月度分区（PolarDB 原生）
- 冷分区（≥ 90 天）转归档表，主表只保留最近 90 天

## 6. PolarDB ↔ SQLite 类型映射

| PolarDB | SQLite | 备注 |
|---|---|---|
| `BIGINT UNSIGNED` | `INTEGER` | SQLite 无无符号；用 INTEGER 64-bit |
| `DATETIME(3)` | `TEXT` ISO 8601 | SQLite 无原生 datetime；存 `'2026-04-28T08:00:00.123Z'` |
| `JSON` | `TEXT` | SQLite JSON1 扩展可选；查询少时直接 TEXT |
| `ENUM(...)` | `TEXT CHECK(... IN (...))` | SQLite 无 ENUM；CHECK 约束模拟 |
| `TINYINT(1)` | `INTEGER` 0/1 | bool |
| `DECIMAL(p,s)` | `REAL` | SQLite 无定点；接受精度损失 |
| `ON UPDATE CURRENT_TIMESTAMP` | TRIGGER | SQLite 不支持；用 BEFORE UPDATE TRIGGER |
| 外键 | 同名 | SQLite 需 `PRAGMA foreign_keys = ON` |
| 月分区 | 不支持 | SQLite 用单表 + 应用侧归档 |

`infra/storage/` 抽象层屏蔽这些差异；业务代码不感知。

## 7. Schema 演进

### 7.1 原则

- **Drop-and-recreate**：v1 阶段 schema 可以推倒重建（与外部 task 项目协同）
- **不写 ALTER TABLE 回填脚本**：迁移成本高，不写就不写
- **本 spec rev bump 即触发 migration**：每次 rev 升级附带 `migrations/v<rev>.sql` 文件

### 7.2 兼容性

破坏性变更（删字段 / 改类型 / 改 ENUM 取值）必须：
- 在本 spec 修订历史前缀加 **[breaking]**
- 提前 1 周通知外部 task 项目（涉及 §4.1 时）
- 推迟到下个 release window

## 8. 与外部 Task 项目的对接边界

### 8.1 谁拥有什么

| 表 | 持有方 | 说明 |
|---|---|---|
| §4.1 任务管理 8 张表 | **外部 task 项目** | 实现遵循本 spec |
| §4.2 ~ §4.6 共 13 张表 | **本仓库** | 由 `infra/storage/` 创建与维护 |

### 8.2 跨边界 SQL 行为

- 本仓库 worker 通过外部 task 项目的 HTTP API 拿 `crawl_task` 数据，**不直接 JOIN**
- 本仓库表中 `task_id` 字段与外部 `crawl_task.task_id` 同语义，但**不建数据库级 FK**（跨库无法约束）
- `task_id` 一致性靠 API 契约保证：未知 task_id 拒收

### 8.3 必备 API（外部项目侧）

- `POST /v1/tasks` —— 创建任务
- `GET /v1/tasks/{id}` —— 拉单个任务（含子表展开）
- `PATCH /v1/tasks/{id}/heartbeat` —— 心跳
- `POST /v1/tasks/{id}/audit` —— 写审计事件
- `POST /v1/tasks/{id}/state` —— 状态迁移（generation / execution）

## 9. 不在本 spec 范围

- 业务专属表（`policy_doc`、`policy_similar_cluster` 等）—— 在各业务 spec 内
- 数据库连接 / 连接池 / 事务边界 —— 由 `infra/storage/` 实现
- 备份与容灾策略 —— 运维侧
- 跨数据中心复制 —— 推迟（TD-004 之后）

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 5 | 2026-04-29 | `crawl_task_execution.adapter_host` 注释同步 source 聚合目录命名，不改变字段类型与索引 | `codegen-output-contract.md` rev 11 |
| rev 4 | 2026-04-29 | 将 `crawl_task.politeness_rps` 默认值从 0.500 调整为 1.000；无明确站点限速时按 1 rps，站点 seed / task 仍可向下覆盖 | `infra-fetch-policy.md` rev 3 |
| rev 3 | 2026-04-29 | `crawl_task_execution` 新增结构化失败原因字段：`last_error_kind`、`last_error_detail`、`last_eval_path`、`needs_manual_review`；明确状态机不承载具体失败类型，MIIT wap search 这类入口问题用 `source_entry_unusable` 记录 | `docs/codegen-pipeline.md` §4.6 |
| rev 2 | 2026-04-28 | 新增 `webui_audit`（§4.7）—— webui 写操作的细粒度审计日志；明确 `crawl_task.created_by` 由 webui 写入时填认证用户 email/sub，与 codegen 链路的 `crawl_task_audit_event` 不重叠 | `webui.md` rev 2 |
| rev 1 | 2026-04-28 | 初稿 —— 13 张本仓库表 + 外部 task 项目 8 张表的 schema 标准；最小化 JSON（仅 `crawl_raw.data` / `metric_snapshot.labels_json` / `task_checkpoint.cursor_extra` / `task_checkpoint.frontier_snapshot_uri` 4 处保留）；数组用子表；状态用 ENUM；含 PolarDB↔SQLite 映射表 | — |
