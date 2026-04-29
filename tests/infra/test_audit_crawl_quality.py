from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from infra.storage.sqlite_store import SqliteMetadataStore
from scripts.audit_crawl_quality import DEFAULT_THRESHOLDS, audit, evaluate


def _init_db(path: Path) -> None:
    store = SqliteMetadataStore(path)
    store.init_schema()
    store.close()


def _insert_raw(
    db: Path,
    *,
    task_id: int,
    url: str,
    body_len: int,
    body_text: str | None = None,
) -> None:
    data = {
        "title": f"title-{body_len}",
        "body_text": body_text if body_text is not None else "正文" * (body_len // 2),
        "source_metadata": {"raw": {"发布时间": "2026-04-29"}},
        "attachments": [],
    }
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute(
                """INSERT INTO crawl_raw
                (task_id, business_context, host, url, canonical_url, url_hash,
                 content_sha256, raw_blob_uri, data)
                VALUES (?, 'gov_policy', 'example.gov.cn', ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    url,
                    url,
                    f"hash-{body_len}",
                    f"sha-{body_len}",
                    f"raw://{body_len}",
                    json.dumps(data, ensure_ascii=False),
                ),
            )
    finally:
        conn.close()


def test_default_audit_threshold_uses_body_100_not_body_500(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _init_db(db)
    for i, body_len in enumerate((120, 180, 220, 260), start=1):
        _insert_raw(db, task_id=1, url=f"https://example.gov.cn/{i}.html", body_len=body_len)

    report = audit(db_path=db, task_id=1)
    verdict, fails = evaluate(report, DEFAULT_THRESHOLDS)

    assert report["rates"]["body_100_rate"] == 1.0
    assert report["rates"]["body_500_rate"] == 0.0
    assert verdict == "pass"
    assert fails == []


def test_audit_fails_script_noise_by_default(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _init_db(db)
    _insert_raw(
        db,
        task_id=1,
        url="https://example.gov.cn/1.html",
        body_len=200,
        body_text="正文" * 80 + " var shareDes = `polluted`; document.write('x')",
    )

    report = audit(db_path=db, task_id=1)
    verdict, fails = evaluate(report, DEFAULT_THRESHOLDS)

    assert report["rates"]["script_noise_rate"] == 1.0
    assert verdict == "fail"
    assert any("script_noise_rate" in fail for fail in fails)
