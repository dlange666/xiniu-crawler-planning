"""T-20260427-102 验收：写入/读取一条 url_record 与 raw_blob，dev profile 通过。"""

from __future__ import annotations

from pathlib import Path

import pytest

from infra.storage import (
    LocalFsBlobStore,
    SqliteMetadataStore,
    get_blob_store,
    get_metadata_store,
)


@pytest.fixture
def tmp_metadata(tmp_path: Path) -> SqliteMetadataStore:
    store = SqliteMetadataStore(tmp_path / "test.db")
    store.init_schema()
    yield store
    store.close()


@pytest.fixture
def tmp_blobstore(tmp_path: Path) -> LocalFsBlobStore:
    return LocalFsBlobStore(tmp_path / "raw")


def test_metadata_init_schema_idempotent(tmp_metadata: SqliteMetadataStore) -> None:
    # 调两次不报错
    tmp_metadata.init_schema()
    tmp_metadata.init_schema()
    rows = tmp_metadata.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = {r[0] for r in rows}
    assert {"url_record", "fetch_record", "crawl_raw", "crawl_run_log"} <= table_names


def test_url_record_upsert_and_idempotent(tmp_metadata: SqliteMetadataStore) -> None:
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="abc123", url="https://x.com/a",
        host="x.com", depth=0, parent_url_fp=None, discovery_source="seed")
    # 重复 upsert 不应再插入
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="abc123", url="https://x.com/a",
        host="x.com", depth=0, parent_url_fp=None, discovery_source="seed")
    rows = tmp_metadata.fetch_all(
        "SELECT url_fp, host, frontier_state FROM url_record")
    assert len(rows) == 1
    assert rows[0] == ("abc123", "x.com", "pending")


def test_crawl_raw_dedup_by_url_hash(tmp_metadata: SqliteMetadataStore) -> None:
    args = dict(
        task_id=1, business_context="gov_policy", host="x.com",
        url="https://x.com/a", canonical_url="https://x.com/a",
        url_hash="hash-1", content_sha256="sha-1",
        raw_blob_uri="file:///tmp/a", data_json='{"k":"v"}',
        etag=None, last_modified=None, run_id="run-1",
    )
    assert tmp_metadata.insert_crawl_raw(**args) is True
    # 同 url_hash 再插 → False（去重）
    assert tmp_metadata.insert_crawl_raw(**args) is False
    assert tmp_metadata.count_crawl_raw(1) == 1


def test_blob_put_get(tmp_blobstore: LocalFsBlobStore) -> None:
    uri = tmp_blobstore.put("2026/04/28/a.html", b"<html>hi</html>", "text/html")
    assert uri.startswith("file://")
    assert tmp_blobstore.exists("2026/04/28/a.html")
    assert tmp_blobstore.get("2026/04/28/a.html") == b"<html>hi</html>"
    s = tmp_blobstore.stat("2026/04/28/a.html")
    assert s["size"] == len(b"<html>hi</html>")


def test_blob_path_escape_rejected(tmp_blobstore: LocalFsBlobStore) -> None:
    with pytest.raises(ValueError, match="escape"):
        tmp_blobstore.put("../escape.txt", b"x")


def test_factory_dev_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_PROFILE", "dev")
    monkeypatch.setenv("CRAWLER_DB_PATH", str(tmp_path / "f.db"))
    monkeypatch.setenv("CRAWLER_BLOB_ROOT", str(tmp_path / "raw"))
    md = get_metadata_store()
    bl = get_blob_store()
    md.init_schema()
    bl.put("k.txt", b"data")
    md.close()


def test_factory_prod_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_PROFILE", "prod")
    with pytest.raises(NotImplementedError):
        get_metadata_store()
    with pytest.raises(NotImplementedError):
        get_blob_store()


def test_factory_unknown_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_PROFILE", "weird")
    with pytest.raises(ValueError, match="unknown STORAGE_PROFILE"):
        get_metadata_store()
