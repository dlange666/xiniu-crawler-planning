"""T-20260428-301: WebUI pages, API wiring, auth, and audit."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra.storage.sqlite_store import SqliteMetadataStore
from webui.app import create_app
from webui.config import WebuiConfig


def make_client(tmp_path: Path, *, role: str = "operator") -> TestClient:
    config = WebuiConfig(
        db_path=tmp_path / "webui.db",
        dev_user="alice@local",
        dev_role=role,
    )
    return TestClient(create_app(config))


def seed_task(db_path: Path) -> int:
    store = SqliteMetadataStore(db_path)
    store.init_schema()
    task_id = None
    try:
        store.execute(
            """INSERT INTO crawl_task
            (business_context, task_type, site_url, host, data_kind, created_by)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "gov_policy",
                "create",
                "https://www.ndrc.gov.cn/xwdt/ztzl/",
                "www.ndrc.gov.cn",
                "policy",
                "seed@local",
            ),
        )
        row = store.fetch_one("SELECT task_id FROM crawl_task ORDER BY task_id DESC LIMIT 1")
        task_id = int(row[0])
        store.execute(
            "INSERT INTO crawl_task_execution (task_id, status) VALUES (?, ?)",
            (task_id, "running"),
        )
        store.insert_fetch_record(
            task_id=task_id,
            url_fp="fp-1",
            status_code=200,
            content_type="text/html",
            bytes_received=128,
            latency_ms=10,
            etag=None,
            last_modified=None,
            error_kind=None,
            error_detail=None,
        )
        store.upsert_url_record(
            task_id=task_id,
            url_fp="fp-1",
            url="https://www.ndrc.gov.cn/a.html",
            host="www.ndrc.gov.cn",
            depth=1,
            parent_url_fp=None,
            discovery_source="list_to_detail",
        )
        store.mark_url_record_state(task_id=task_id, url_fp="fp-1", state="done")
        store.upsert_url_record(
            task_id=task_id,
            url_fp="fp-2",
            url="https://www.ndrc.gov.cn/b.html",
            host="www.ndrc.gov.cn",
            depth=2,
            parent_url_fp="fp-1",
            discovery_source="anchor",
        )
        store.insert_crawl_raw(
            task_id=task_id,
            business_context="gov_policy",
            host="www.ndrc.gov.cn",
            url="https://www.ndrc.gov.cn/a.html",
            canonical_url="https://www.ndrc.gov.cn/a.html",
            url_hash="hash-1",
            content_sha256="sha-1",
            raw_blob_uri="file:///tmp/a.html",
            data_json=json.dumps(
                {
                    "title": "政策样例",
                    "body_text": "正文内容",
                    "source_metadata": {"发布机关": "NDRC"},
                    "attachments": [],
                },
                ensure_ascii=False,
            ),
            etag=None,
            last_modified=None,
            run_id="run-1",
        )
    finally:
        store.close()
    assert task_id is not None
    return task_id


def test_pages_render_and_api_data_is_available(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = seed_task(tmp_path / "webui.db")

    for path in ["/", "/tasks", f"/tasks/{task_id}", f"/tasks/{task_id}/items", "/monitor"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    api_response = client.get("/api/tasks")
    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["items"][0]["task_id"] == task_id
    assert payload["items"][0]["host"] == "www.ndrc.gov.cn"

    ts_response = client.get(f"/api/tasks/{task_id}/timeseries")
    assert ts_response.status_code == 200
    assert ts_response.json()["series"][0]["name"] == "fetches"

    detail_response = client.get(f"/api/tasks/{task_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["task"]["task_id"] == task_id
    assert detail_payload["url_total"] == 2
    assert detail_payload["fetched_total"] == 1
    assert detail_payload["jump_total"] == 1

    urls_response = client.get(f"/api/tasks/{task_id}/urls")
    assert urls_response.status_code == 200
    urls_payload = urls_response.json()
    assert urls_payload["total"] == 2
    assert urls_payload["limit"] == 100
    assert urls_payload["offset"] == 0
    assert urls_payload["depth_summary"] == [
        {"depth": 1, "url_count": 1},
        {"depth": 2, "url_count": 1},
    ]
    assert urls_payload["items"][0]["depth"] == 1
    assert urls_payload["items"][0]["frontier_state"] == "done"
    assert urls_payload["items"][0]["raw_title"] == "政策样例"

    fetched_response = client.get(f"/api/tasks/{task_id}/urls?kind=fetched")
    assert fetched_response.status_code == 200
    fetched_payload = fetched_response.json()
    assert fetched_payload["total"] == 1
    assert fetched_payload["items"][0]["link_kind"] == "fetched"
    assert fetched_payload["items"][0]["raw_title"] == "政策样例"

    jump_response = client.get(f"/api/tasks/{task_id}/urls?kind=jump&depth=2")
    assert jump_response.status_code == 200
    jump_payload = jump_response.json()
    assert jump_payload["total"] == 1
    assert jump_payload["depth"] == 2
    assert jump_payload["items"][0]["link_kind"] == "jump"
    assert jump_payload["items"][0]["parent_url_fp"] == "fp-1"

    detail_html = client.get(f"/tasks/{task_id}").text
    assert "Source URL 明细" in detail_html
    assert "1-2" in detail_html
    assert "depth 1" in detail_html
    assert "政策样例" in detail_html


def test_react_spa_endpoint_serves_html(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/ui/tasks")
    assert response.status_code in {200, 503}
    assert "text/html" in response.headers["content-type"]


def test_create_task_writes_created_by_and_webui_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/tasks",
        data={
            "business_context": "gov_policy",
            "site_url": "https://www.ndrc.gov.cn/xwdt/",
            "data_kind": "policy",
            "crawl_mode": "full",
            "scope_mode": "same_origin",
            "politeness_rps": "0.5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    conn = sqlite3.connect(tmp_path / "webui.db")
    try:
        created_by = conn.execute("SELECT created_by FROM crawl_task").fetchone()[0]
        audit = conn.execute(
            "SELECT actor, role, action FROM webui_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert created_by == "alice@local"
    assert audit == ("alice@local", "operator", "submit_task")


def test_viewer_cannot_write(tmp_path: Path) -> None:
    client = make_client(tmp_path, role="viewer")
    response = client.post(
        "/tasks",
        data={"site_url": "https://www.ndrc.gov.cn/"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_production_rejects_dev_auth(tmp_path: Path) -> None:
    config = WebuiConfig(
        db_path=tmp_path / "webui.db",
        env="production",
        auth_mode="dev",
    )
    with pytest.raises(RuntimeError, match="forbids"):
        create_app(config)
