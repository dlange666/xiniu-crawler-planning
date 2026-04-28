"""SQLite 元数据存储（dev profile）。

schema 来自 docs/prod-spec/data-model.md，类型按 §6 PolarDB↔SQLite 映射收敛。
MVP 阶段仅实现采集链路必备表：
  - url_record
  - fetch_record
  - crawl_raw
  - crawl_run_log

任务表（crawl_task / generation / execution / run）由外部 task 项目持有，
本仓库 worker 仅消费 task_id；MVP 直接通过命令行参数注入 task_id，不建表。
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

    def insert_fetch_record(self, *, task_id: int, url_fp: str, attempt: int,
                            status_code: int | None, content_type: str | None,
                            bytes_received: int | None, latency_ms: int | None,
                            etag: str | None, last_modified: str | None,
                            error_kind: str | None, error_detail: str | None) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO fetch_record
                (task_id, url_fp, attempt, status_code, content_type, bytes_received,
                 latency_ms, etag, last_modified, error_kind, error_detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, url_fp, attempt, status_code, content_type, bytes_received,
                 latency_ms, etag, last_modified, error_kind, error_detail),
            )

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

    def count_crawl_raw(self, task_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM crawl_raw WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()
