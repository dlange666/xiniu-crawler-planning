"""SQLite 元数据存储（dev profile）。

schema 来自 docs/prod-spec/data-model.md，类型按 §6 PolarDB↔SQLite 映射收敛。
MVP 阶段实现采集链路与 WebUI 必备表：
  - crawl_task
  - crawl_task_execution
  - url_record
  - fetch_record
  - crawl_raw
  - crawl_run_log
  - webui_audit

codegen 的外部 task 项目仍由 TaskSource 抽象对接；WebUI MVP 在本仓库维护
采集任务后台所需的 crawl_task 子集。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# DDL 收敛自 data-model.md，按 SQLite 类型映射调整：
# - DATETIME(3) → TEXT (ISO 8601)
# - ENUM(...) → TEXT CHECK(... IN (...))
# - JSON → TEXT
# - BIGINT UNSIGNED AUTO_INCREMENT → INTEGER PRIMARY KEY AUTOINCREMENT
# - DECIMAL → REAL
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crawl_task (
    task_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    business_context        TEXT NOT NULL,
    task_type               TEXT NOT NULL DEFAULT 'create'
                            CHECK(task_type IN ('create','update','extend')),
    site_url                TEXT NOT NULL,
    host                    TEXT NOT NULL,
    data_kind               TEXT NOT NULL DEFAULT 'policy',
    scope_description       TEXT,
    scope_mode              TEXT NOT NULL DEFAULT 'same_origin'
                            CHECK(scope_mode IN (
                                'same_origin','same_etld_plus_one',
                                'url_pattern','allowlist'
                            )),
    scope_url_pattern       TEXT,
    scope_follow_canonical  INTEGER NOT NULL DEFAULT 1,
    scope_follow_pagination INTEGER NOT NULL DEFAULT 1,
    crawl_mode              TEXT NOT NULL DEFAULT 'full'
                            CHECK(crawl_mode IN ('full','incremental')),
    crawl_until             TEXT,
    full_crawl_cron         TEXT,
    max_pages_per_run       INTEGER,
    run_frequency           TEXT NOT NULL DEFAULT 'once',
    schedule_time           TEXT,
    schedule_minute         INTEGER,
    robots_strict           INTEGER NOT NULL DEFAULT 1,
    politeness_rps          REAL NOT NULL DEFAULT 1.000,
    purpose                 TEXT,
    legal_basis             TEXT,
    responsible_party       TEXT,
    priority                INTEGER NOT NULL DEFAULT 5,
    created_by              TEXT,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_crawl_task_context_kind
    ON crawl_task(business_context, data_kind);
CREATE INDEX IF NOT EXISTS idx_crawl_task_host ON crawl_task(host);
CREATE INDEX IF NOT EXISTS idx_crawl_task_created ON crawl_task(created_at DESC);

CREATE TABLE IF NOT EXISTS crawl_task_execution (
    task_id                INTEGER PRIMARY KEY,
    status                 TEXT NOT NULL DEFAULT 'scheduled'
                           CHECK(status IN (
                               'scheduled','running',
                               'canary_stage_0','canary_stage_1',
                               'canary_stage_2','canary_stage_3',
                               'completed','failed','disabled','rolled_back'
                           )),
    adapter_host           TEXT,
    adapter_schema_version INTEGER,
    next_run_at            TEXT,
    last_run_at            TEXT,
    last_run_id            TEXT,
    last_run_status        TEXT,
    last_full_crawl_at     TEXT,
    canary_stage_until     TEXT,
    run_count              INTEGER NOT NULL DEFAULT 0,
    consecutive_failures   INTEGER NOT NULL DEFAULT 0,
    worker_id              TEXT,
    claim_at               TEXT,
    heartbeat_at           TEXT,
    FOREIGN KEY (task_id) REFERENCES crawl_task(task_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_crawl_task_execution_status_next
    ON crawl_task_execution(status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_crawl_task_execution_adapter
    ON crawl_task_execution(adapter_host);

CREATE TABLE IF NOT EXISTS url_record (
    task_id              INTEGER NOT NULL,
    url_fp               TEXT NOT NULL,
    url                  TEXT NOT NULL,
    canonical_url        TEXT NOT NULL,
    host                 TEXT NOT NULL,
    etld_plus_one        TEXT NOT NULL,
    depth                INTEGER NOT NULL DEFAULT 0,
    parent_url_fp        TEXT,
    discovery_source     TEXT,
    priority_score       REAL NOT NULL DEFAULT 0.5,
    scope_decision       TEXT NOT NULL DEFAULT 'accepted'
                         CHECK(scope_decision IN (
                             'accepted','rejected_scope',
                             'rejected_robots','rejected_dedup'
                         )),
    frontier_state       TEXT NOT NULL DEFAULT 'pending'
                         CHECK(frontier_state IN ('pending','in_flight','done','failed','dlq')),
    etag                 TEXT,
    last_modified        TEXT,
    last_content_sha256  TEXT,
    last_fetched_at      TEXT,
    attempts             INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (task_id, url_fp)
);
CREATE INDEX IF NOT EXISTS idx_url_record_task_state ON url_record(task_id, frontier_state);
CREATE INDEX IF NOT EXISTS idx_url_record_host ON url_record(host);

CREATE TABLE IF NOT EXISTS fetch_record (
    fetch_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL,
    url_fp          TEXT NOT NULL,
    attempt         INTEGER NOT NULL DEFAULT 1,
    status_code     INTEGER,
    rendered        INTEGER NOT NULL DEFAULT 0,
    content_type    TEXT,
    bytes_received  INTEGER,
    latency_ms      INTEGER,
    etag            TEXT,
    last_modified   TEXT,
    error_kind      TEXT,
    error_detail    TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (task_id, url_fp, attempt)
);
CREATE INDEX IF NOT EXISTS idx_fetch_record_task ON fetch_record(task_id, fetched_at DESC);

CREATE TABLE IF NOT EXISTS crawl_raw (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            INTEGER NOT NULL,
    business_context   TEXT NOT NULL,
    host               TEXT NOT NULL,
    url                TEXT NOT NULL,
    canonical_url      TEXT NOT NULL,
    url_hash           TEXT NOT NULL UNIQUE,
    content_sha256     TEXT NOT NULL,
    raw_blob_uri       TEXT NOT NULL,
    data               TEXT NOT NULL,
    etag               TEXT,
    last_modified      TEXT,
    run_id             TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_crawl_raw_task ON crawl_raw(task_id);
CREATE INDEX IF NOT EXISTS idx_crawl_raw_context_host ON crawl_raw(business_context, host);
CREATE INDEX IF NOT EXISTS idx_crawl_raw_content_sha ON crawl_raw(content_sha256);

CREATE TABLE IF NOT EXISTS crawl_run_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            INTEGER NOT NULL,
    run_id             TEXT NOT NULL,
    business_context   TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'running'
                       CHECK(status IN ('running','completed','failed')),
    items_count        INTEGER NOT NULL DEFAULT 0,
    error              TEXT,
    started_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_crawl_run_log_task ON crawl_run_log(task_id);

CREATE TABLE IF NOT EXISTS webui_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    actor        TEXT NOT NULL,
    role         TEXT NOT NULL,
    action       TEXT NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    payload      TEXT,
    ip           TEXT,
    user_agent   TEXT,
    request_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_webui_audit_actor_ts ON webui_audit(actor, ts DESC);
CREATE INDEX IF NOT EXISTS idx_webui_audit_action_ts ON webui_audit(action, ts DESC);
CREATE INDEX IF NOT EXISTS idx_webui_audit_target ON webui_audit(target_type, target_id);
"""


class SqliteMetadataStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")

    def init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._conn:
            self._conn.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> tuple | None:
        cur = self._conn.execute(sql, params)
        return cur.fetchone()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def upsert_url_record(self, *, task_id: int, url_fp: str, url: str, host: str,
                          depth: int, parent_url_fp: str | None,
                          discovery_source: str) -> None:
        # 计算 etld_plus_one：本 MVP 退化为 host 自身（无 publicsuffix 依赖）
        etld_plus_one = host
        canonical_url = url
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO url_record
                (task_id, url_fp, url, canonical_url, host, etld_plus_one,
                 depth, parent_url_fp, discovery_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, url_fp, url, canonical_url, host, etld_plus_one,
                 depth, parent_url_fp, discovery_source),
            )

    def mark_url_record_state(self, *, task_id: int, url_fp: str, state: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE url_record SET frontier_state=?, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE task_id=? AND url_fp=?",
                (state, task_id, url_fp),
            )

    def list_pending_url_records(self, *, task_id: int) -> list[dict]:
        cur = self._conn.execute(
            """SELECT url, url_fp, host, depth, parent_url_fp, discovery_source
            FROM url_record
            WHERE task_id=? AND frontier_state='pending'
            ORDER BY depth ASC, url_fp ASC""",
            (task_id,),
        )
        return [
            {
                "url": r[0], "url_fp": r[1], "host": r[2],
                "depth": r[3], "parent_url_fp": r[4],
                "discovery_source": r[5],
            }
            for r in cur.fetchall()
        ]

    def has_url_records_for_task(self, *, task_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM url_record WHERE task_id=? LIMIT 1", (task_id,))
        return cur.fetchone() is not None

    def insert_fetch_record(self, *, task_id: int, url_fp: str,
                            status_code: int | None, content_type: str | None,
                            bytes_received: int | None, latency_ms: int | None,
                            etag: str | None, last_modified: str | None,
                            error_kind: str | None, error_detail: str | None) -> int:
        """attempt 自动递增 = max(已有) + 1。

        重启续抓时同 (task_id, url_fp) 的下一次 attempt 会取 N+1，避免 UNIQUE 冲突。
        """
        with self._conn:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(attempt), 0) FROM fetch_record "
                "WHERE task_id=? AND url_fp=?", (task_id, url_fp),
            )
            row = cur.fetchone()
            next_attempt = (row[0] if row else 0) + 1
            self._conn.execute(
                """INSERT INTO fetch_record
                (task_id, url_fp, attempt, status_code, content_type, bytes_received,
                 latency_ms, etag, last_modified, error_kind, error_detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, url_fp, next_attempt, status_code, content_type, bytes_received,
                 latency_ms, etag, last_modified, error_kind, error_detail),
            )
        return next_attempt

    def insert_crawl_raw(self, *, task_id: int, business_context: str, host: str,
                         url: str, canonical_url: str, url_hash: str,
                         content_sha256: str, raw_blob_uri: str, data_json: str,
                         etag: str | None, last_modified: str | None,
                         run_id: str | None) -> bool:
        try:
            with self._conn:
                self._conn.execute(
                    """INSERT INTO crawl_raw
                    (task_id, business_context, host, url, canonical_url, url_hash,
                     content_sha256, raw_blob_uri, data, etag, last_modified, run_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (task_id, business_context, host, url, canonical_url, url_hash,
                     content_sha256, raw_blob_uri, data_json, etag, last_modified, run_id),
                )
            return True
        except sqlite3.IntegrityError:
            # url_hash UNIQUE 冲突 → 已存在
            return False

    def is_url_in_crawl_raw(self, *, url_hash: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM crawl_raw WHERE url_hash = ? LIMIT 1", (url_hash,))
        return cur.fetchone() is not None

    def count_crawl_raw(self, task_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM crawl_raw WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()
