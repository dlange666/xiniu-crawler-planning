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

    def insert_fetch_record(self, *, task_id: int, url_fp: str, attempt: int,
                            status_code: int | None, content_type: str | None,
                            bytes_received: int | None, latency_ms: int | None,
                            etag: str | None, last_modified: str | None,
                            error_kind: str | None, error_detail: str | None) -> None: ...

    def insert_crawl_raw(self, *, task_id: int, business_context: str, host: str,
                         url: str, canonical_url: str, url_hash: str,
                         content_sha256: str, raw_blob_uri: str, data_json: str,
                         etag: str | None, last_modified: str | None,
                         run_id: str | None) -> bool:
        """写入 crawl_raw；返回 True=新增 / False=已存在（按 url_hash 去重）。"""
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
