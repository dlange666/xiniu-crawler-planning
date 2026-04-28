"""Storage abstraction layer.

实现 spec: docs/prod-spec/data-model.md §6 (PolarDB ↔ SQLite 类型映射).

通过 STORAGE_PROFILE 环境变量切换实现：
  - dev  → SqliteMetadataStore + LocalFsBlobStore
  - prod → 暂未实现（PolarDB + 阿里云 OSS）

业务代码只 import 抽象工厂，不直接持有具体实现。
"""

from __future__ import annotations

import os
from pathlib import Path

from .local_fs_store import LocalFsBlobStore
from .protocols import BlobStore, MetadataStore
from .sqlite_store import SqliteMetadataStore

__all__ = [
    "BlobStore",
    "MetadataStore",
    "get_blob_store",
    "get_metadata_store",
]


def _profile() -> str:
    return os.environ.get("STORAGE_PROFILE", "dev")


def get_metadata_store() -> MetadataStore:
    profile = _profile()
    if profile == "dev":
        db_path = Path(os.environ.get("CRAWLER_DB_PATH", "runtime/db/dev.db"))
        return SqliteMetadataStore(db_path)
    if profile == "prod":
        msg = "PolarDB metadata store not yet implemented (prod profile)"
        raise NotImplementedError(msg)
    msg = f"unknown STORAGE_PROFILE={profile!r}"
    raise ValueError(msg)


def get_blob_store() -> BlobStore:
    profile = _profile()
    if profile == "dev":
        root = Path(os.environ.get("CRAWLER_BLOB_ROOT", "runtime/raw"))
        return LocalFsBlobStore(root)
    if profile == "prod":
        msg = "Aliyun OSS blob store not yet implemented (prod profile)"
        raise NotImplementedError(msg)
    msg = f"unknown STORAGE_PROFILE={profile!r}"
    raise ValueError(msg)
