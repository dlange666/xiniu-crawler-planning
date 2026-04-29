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
    columns = {
        r[1] for r in tmp_metadata.fetch_all("PRAGMA table_info(crawl_task_execution)")
    }
    assert {
        "last_error_kind",
        "last_error_detail",
        "last_eval_path",
        "needs_manual_review",
    } <= columns


def test_metadata_init_schema_migrates_existing_execution_table(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    store = SqliteMetadataStore(db)
    store.execute(
        """CREATE TABLE crawl_task_execution (
            task_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'scheduled',
            adapter_host TEXT,
            adapter_schema_version INTEGER,
            next_run_at TEXT,
            last_run_at TEXT,
            last_run_id TEXT,
            last_run_status TEXT,
            last_full_crawl_at TEXT,
            canary_stage_until TEXT,
            run_count INTEGER NOT NULL DEFAULT 0,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            worker_id TEXT,
            claim_at TEXT,
            heartbeat_at TEXT
        )"""
    )

    store.init_schema()

    columns = {r[1] for r in store.fetch_all("PRAGMA table_info(crawl_task_execution)")}
    assert {
        "last_error_kind",
        "last_error_detail",
        "last_eval_path",
        "needs_manual_review",
    } <= columns
    store.close()


def test_crawl_task_default_politeness_rps_is_one(tmp_metadata: SqliteMetadataStore) -> None:
    tmp_metadata.execute(
        """INSERT INTO crawl_task
        (business_context, site_url, host)
        VALUES ('gov_policy', 'https://example.gov.cn/', 'example.gov.cn')"""
    )

    row = tmp_metadata.fetch_one("SELECT politeness_rps FROM crawl_task")

    assert row == (1.0,)


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


def test_fetch_record_attempt_auto_increments(tmp_metadata: SqliteMetadataStore) -> None:
    """重启续抓 bug 修复：attempt 由 storage 自动计算，不再因 UNIQUE 冲突崩溃。"""
    base_args = dict(
        task_id=1, url_fp="abc123",
        status_code=200, content_type="text/html",
        bytes_received=100, latency_ms=10,
        etag=None, last_modified=None,
        error_kind=None, error_detail=None,
    )
    # 第一次写入 → attempt=1
    a1 = tmp_metadata.insert_fetch_record(**base_args)
    assert a1 == 1
    # 重启场景：再次写入同 (task_id, url_fp) → attempt 自动 +1
    a2 = tmp_metadata.insert_fetch_record(**base_args)
    assert a2 == 2
    # 第三次再来一次
    a3 = tmp_metadata.insert_fetch_record(**base_args)
    assert a3 == 3
    rows = tmp_metadata.fetch_all(
        "SELECT attempt FROM fetch_record WHERE task_id=? AND url_fp=? ORDER BY attempt",
        (1, "abc123"))
    assert [r[0] for r in rows] == [1, 2, 3]


def test_fetch_record_attempt_independent_per_url(tmp_metadata: SqliteMetadataStore) -> None:
    """不同 url_fp 的 attempt 互相独立。"""
    base = dict(
        task_id=1, status_code=200, content_type=None,
        bytes_received=1, latency_ms=1,
        etag=None, last_modified=None,
        error_kind=None, error_detail=None,
    )
    assert tmp_metadata.insert_fetch_record(url_fp="A", **base) == 1
    assert tmp_metadata.insert_fetch_record(url_fp="B", **base) == 1
    assert tmp_metadata.insert_fetch_record(url_fp="A", **base) == 2
    assert tmp_metadata.insert_fetch_record(url_fp="B", **base) == 2


def test_is_url_in_crawl_raw(tmp_metadata: SqliteMetadataStore) -> None:
    """重启续抓：is_url_in_crawl_raw 用于跳过已抓 URL。"""
    assert tmp_metadata.is_url_in_crawl_raw(url_hash="not-yet") is False
    tmp_metadata.insert_crawl_raw(
        task_id=1, business_context="gov_policy", host="x.com",
        url="https://x.com/a", canonical_url="https://x.com/a",
        url_hash="hash-A", content_sha256="sha",
        raw_blob_uri="file:///tmp/a", data_json="{}",
        etag=None, last_modified=None, run_id=None,
    )
    assert tmp_metadata.is_url_in_crawl_raw(url_hash="hash-A") is True
    assert tmp_metadata.is_url_in_crawl_raw(url_hash="hash-B") is False


def test_url_record_state_transitions(tmp_metadata: SqliteMetadataStore) -> None:
    """checkpoint 恢复：mark_url_record_state 改 frontier_state 列。"""
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="fp-1", url="https://x.com/a",
        host="x.com", depth=0, parent_url_fp=None, discovery_source="seed")
    rows = tmp_metadata.fetch_all(
        "SELECT frontier_state FROM url_record WHERE url_fp='fp-1'")
    assert rows[0][0] == "pending"

    tmp_metadata.mark_url_record_state(task_id=1, url_fp="fp-1", state="done")
    rows = tmp_metadata.fetch_all(
        "SELECT frontier_state FROM url_record WHERE url_fp='fp-1'")
    assert rows[0][0] == "done"


def test_list_pending_url_records_orders_by_depth(
        tmp_metadata: SqliteMetadataStore) -> None:
    """list_pending_url_records 按 depth 升序返回，过滤掉非 pending。"""
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="fp-D2", url="https://x.com/d2",
        host="x.com", depth=2, parent_url_fp="fp-D1",
        discovery_source="detail_to_interpret")
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="fp-D0", url="https://x.com/d0",
        host="x.com", depth=0, parent_url_fp=None, discovery_source="list_page")
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="fp-D1", url="https://x.com/d1",
        host="x.com", depth=1, parent_url_fp="fp-D0",
        discovery_source="list_to_detail")
    # 标 D0 done → 不应再返回
    tmp_metadata.mark_url_record_state(task_id=1, url_fp="fp-D0", state="done")
    # 跨 task 的不应混入
    tmp_metadata.upsert_url_record(
        task_id=2, url_fp="fp-X", url="https://y.com/x", host="y.com",
        depth=0, parent_url_fp=None, discovery_source="list_page")

    rows = tmp_metadata.list_pending_url_records(task_id=1)
    assert [r["url_fp"] for r in rows] == ["fp-D1", "fp-D2"]
    assert rows[0]["depth"] == 1
    assert rows[0]["discovery_source"] == "list_to_detail"


def test_has_url_records_for_task(tmp_metadata: SqliteMetadataStore) -> None:
    assert tmp_metadata.has_url_records_for_task(task_id=1) is False
    tmp_metadata.upsert_url_record(
        task_id=1, url_fp="fp-1", url="https://x.com/a",
        host="x.com", depth=0, parent_url_fp=None, discovery_source="seed")
    assert tmp_metadata.has_url_records_for_task(task_id=1) is True
    assert tmp_metadata.has_url_records_for_task(task_id=999) is False


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
