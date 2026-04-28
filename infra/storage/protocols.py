"""Storage 抽象协议。

业务代码通过这两个 Protocol 与存储交互；具体实现由 dev/prod profile 切换。
"""

from __future__ import annotations

from typing import Any, Protocol


class MetadataStore(Protocol):
    """元数据 / 业务关系数据存储（SQLite for dev, PolarDB for prod）。"""

    def init_schema(self) -> None:
        """创建表（drop-and-recreate 不在此处；本方法仅 IF NOT EXISTS 创建）。"""
        ...

    def execute(self, sql: str, params: tuple = ()) -> None:
        """执行 DML（INSERT / UPDATE / DELETE）。"""
        ...

    def fetch_one(self, sql: str, params: tuple = ()) -> tuple | None: ...

    def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]: ...

    def upsert_url_record(self, *, task_id: int, url_fp: str, url: str, host: str,
                          depth: int, parent_url_fp: str | None,
                          discovery_source: str) -> None: ...

    def mark_url_record_state(self, *, task_id: int, url_fp: str, state: str) -> None:
        """更新 url_record.frontier_state（pending/in_flight/done/failed/dlq）。"""
        ...

    def list_pending_url_records(self, *, task_id: int) -> list[dict]:
        """列出 task 中 frontier_state='pending' 的 URL；用于重启续抓。

        每行返回 dict：url / url_fp / host / depth / parent_url_fp / discovery_source。
        """
        ...

    def has_url_records_for_task(self, *, task_id: int) -> bool:
        """该 task 是否已有 url_record 行（区分新跑 vs 续抓）。"""
        ...

    def insert_fetch_record(self, *, task_id: int, url_fp: str,
                            status_code: int | None, content_type: str | None,
                            bytes_received: int | None, latency_ms: int | None,
                            etag: str | None, last_modified: str | None,
                            error_kind: str | None, error_detail: str | None) -> int:
        """写入一条 fetch_record；attempt 由实现自动递增（max(已有)+1）。

        重启续抓时不会因 UNIQUE(task_id, url_fp, attempt) 冲突而崩溃。
        返回本次实际写入的 attempt 值。
        """
        ...

    def insert_crawl_raw(self, *, task_id: int, business_context: str, host: str,
                         url: str, canonical_url: str, url_hash: str,
                         content_sha256: str, raw_blob_uri: str, data_json: str,
                         etag: str | None, last_modified: str | None,
                         run_id: str | None) -> bool:
        """写入 crawl_raw；返回 True=新增 / False=已存在（按 url_hash 去重）。"""
        ...

    def is_url_in_crawl_raw(self, *, url_hash: str) -> bool:
        """检查该 url_hash 是否已存在于 crawl_raw（用于重启续抓时跳过已抓 URL）。"""
        ...

    def count_crawl_raw(self, task_id: int) -> int: ...

    def close(self) -> None: ...


class BlobStore(Protocol):
    """原始字节存储（本地 FS for dev, 阿里云 OSS for prod）。"""

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """写入；返回 URI（如 file:///... 或 oss://bucket/key）。"""
        ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def stat(self, key: str) -> dict[str, Any]: ...
