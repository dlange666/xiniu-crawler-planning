from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.ingest_prd_tasks import extract_candidates, infer_data_kind, ingest_candidates


def test_extract_candidates_cleans_urls_and_infers_kind(tmp_path: Path) -> None:
    prd = tmp_path / "sample.md"
    prd.write_text(
        "\n".join(
            [
                "# 数据源",
                "## 上海证券交易所",
                "规则：https://www.sse.com.cn/lawandrules/overview/",
                "新闻：https://www.sse.com.cn/aboutus/mediacenter/hotandd/",
                "动态：https://www.china-cba.net/Index/lists/catid/14.html，"
                "https://www.china-cba.net/Index/lists/catid/32.html",
                "公告：https://www.cfachina.org/（协会公告）",
                "公告：https://www.cfachina.org/（重复）",
            ]
        ),
        encoding="utf-8",
    )

    candidates = extract_candidates(prd)

    assert [c.site_url for c in candidates] == [
        "https://www.sse.com.cn/lawandrules/overview/",
        "https://www.sse.com.cn/aboutus/mediacenter/hotandd/",
        "https://www.china-cba.net/Index/lists/catid/14.html",
        "https://www.china-cba.net/Index/lists/catid/32.html",
        "https://www.cfachina.org/",
    ]
    assert [c.data_kind for c in candidates] == [
        "regulation",
        "news",
        "news",
        "news",
        "announcement",
    ]
    assert candidates[0].host == "www.sse.com.cn"


def test_infer_data_kind_defaults_to_policy() -> None:
    assert infer_data_kind("国务院政策文件库") == "policy"
    assert infer_data_kind("政策解读") == "policy_interpretation"
    assert infer_data_kind("规划信息") == "planning"


def test_ingest_candidates_is_idempotent(tmp_path: Path) -> None:
    prd = tmp_path / "sample.md"
    prd.write_text(
        "\n".join(
            [
                "# 数据源",
                "政策 https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/",
                "新闻 https://www.gov.cn/yaowen/",
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "tasks.db"
    candidates = extract_candidates(prd)

    first = ingest_candidates(
        db,
        candidates,
        actor="test",
        purpose="test purpose",
        legal_basis="public source",
        responsible_party="crawler-team",
        max_pages_per_run=30,
        politeness_rps=0.3,
        dry_run=False,
    )
    second = ingest_candidates(
        db,
        candidates,
        actor="test",
        purpose="test purpose",
        legal_basis="public source",
        responsible_party="crawler-team",
        max_pages_per_run=30,
        politeness_rps=0.3,
        dry_run=False,
    )

    assert first.inserted == 2
    assert second.inserted == 0
    assert second.skipped_existing == 2

    conn = sqlite3.connect(db)
    try:
        task_count = conn.execute("SELECT COUNT(*) FROM crawl_task").fetchone()[0]
        execution_count = conn.execute(
            "SELECT COUNT(*) FROM crawl_task_execution WHERE status='scheduled'"
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT host, data_kind, purpose, legal_basis, responsible_party
            FROM crawl_task ORDER BY task_id"""
        ).fetchall()
    finally:
        conn.close()

    assert task_count == 2
    assert execution_count == 2
    assert rows == [
        (
            "www.ndrc.gov.cn",
            "policy",
            "test purpose",
            "public source",
            "crawler-team",
        ),
        ("www.gov.cn", "news", "test purpose", "public source", "crawler-team"),
    ]
