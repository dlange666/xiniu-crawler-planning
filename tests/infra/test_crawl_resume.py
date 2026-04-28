"""CrawlEngine 续抓恢复测试。

覆盖 健壮性需求：中断后从 checkpoint 恢复，已采集 URL 不再重抓。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from infra.crawl import CrawlEngine
from infra.crawl.types import (
    Attachment,
    ParseDetailResult,
    ParseListResult,
    SeedSpec,
    SourceMetadata,
    TaskSpec,
)


class _FakeAdapter:
    """最小 adapter：给定列表页返回固定详情链接，详情页返回固定结构。"""

    schema_version = 1

    def __init__(self) -> None:
        self.parse_list_calls: list[str] = []
        self.parse_detail_calls: list[str] = []

    def parse_list(self, html: str, base_url: str) -> ParseListResult:
        self.parse_list_calls.append(base_url)
        return ParseListResult(
            detail_links=[
                "https://example.com/p/1",
                "https://example.com/p/2",
            ],
            next_pages=[],
        )

    def parse_detail(self, html: str, base_url: str) -> ParseDetailResult:
        self.parse_detail_calls.append(base_url)
        return ParseDetailResult(
            title=f"title for {base_url}",
            body_text="body",
            source_metadata=SourceMetadata(),
            attachments=[],
            raw_links=[],
            interpret_links=[],
        )


class _FakeResp:
    def __init__(self, url: str, body: bytes = b"<html></html>") -> None:
        self.status_code = 200
        self.body = body
        self.final_url = url
        self.headers = {"content-type": "text/html"}
        self.elapsed_ms = 1
        self.error_kind = None
        self.error_detail = None
        self.anti_bot_signal = False


def _make_engine(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    fetched_urls: list[str],
) -> tuple[CrawlEngine, _FakeAdapter]:
    monkeypatch.setenv("STORAGE_PROFILE", "dev")
    monkeypatch.setenv("CRAWLER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CRAWLER_BLOB_ROOT", str(tmp_path / "blobs"))

    adapter = _FakeAdapter()
    task = TaskSpec(
        task_id=42, business_context="gov_policy",
        strategy="bfs", max_depth=1,
        scope_mode="same_origin",
    )
    seed = SeedSpec(
        host="example.com",
        entry_urls=["https://example.com/list"],
        politeness_rps=10.0,
    )
    engine = CrawlEngine(
        task=task, seed=seed, adapter_resolver=lambda host: adapter,
    )

    # 屏蔽 robots：放行一切
    engine.robots.is_allowed = lambda url: (True, "ok")  # type: ignore[method-assign]

    def fake_fetch(url: str, *, host: str = "", **kwargs: Any) -> _FakeResp:
        fetched_urls.append(url)
        return _FakeResp(url)

    engine.http.fetch = fake_fetch  # type: ignore[method-assign]
    return engine, adapter


def test_first_run_then_resume_skips_already_crawled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首跑写入 url_record + crawl_raw；再跑应识别为续抓，且不重抓已成功 URL。"""
    fetched_urls: list[str] = []
    engine, adapter = _make_engine(
        tmp_path=tmp_path, monkeypatch=monkeypatch, fetched_urls=fetched_urls)
    report = engine.run()
    engine.close()

    assert report.resumed is False
    assert report.list_pages_fetched == 1
    assert report.detail_urls_fetched == 2
    assert report.raw_records_written == 2
    # 首跑应抓 1 列表 + 2 详情 = 3 次 HTTP
    assert len(fetched_urls) == 3

    # 第二次：同 task_id，url_record 仍在 → 应识别为 resumed；
    # 已落 crawl_raw 的详情 URL 不应再 HTTP
    fetched2: list[str] = []
    engine2, _ = _make_engine(
        tmp_path=tmp_path, monkeypatch=monkeypatch, fetched_urls=fetched2)
    report2 = engine2.run()
    engine2.close()

    assert report2.resumed is True
    # 第二次跑时，所有 pending URL 都已 done（首跑全部成功），
    # 所以 urls_resumed 应为 0，主循环也无事可做
    assert report2.urls_resumed == 0
    assert fetched2 == []


def test_resume_picks_up_pending_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模拟首跑半途中断：部分 detail 还是 pending，续抓应继续抓它们。"""
    monkeypatch.setenv("STORAGE_PROFILE", "dev")
    monkeypatch.setenv("CRAWLER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CRAWLER_BLOB_ROOT", str(tmp_path / "blobs"))

    # 直接向 storage 注入"半完成"状态：
    # - 1 个列表页（done）
    # - 2 个详情：fp-D1 已完成（写入 crawl_raw + done），fp-D2 仍 pending
    from infra.storage import get_metadata_store
    md = get_metadata_store()
    md.init_schema()
    md.upsert_url_record(
        task_id=42, url_fp="fp-L", url="https://example.com/list",
        host="example.com", depth=0, parent_url_fp=None,
        discovery_source="list_page")
    md.mark_url_record_state(task_id=42, url_fp="fp-L", state="done")
    md.upsert_url_record(
        task_id=42, url_fp="fp-D1", url="https://example.com/p/1",
        host="example.com", depth=1, parent_url_fp="fp-L",
        discovery_source="list_to_detail")
    md.mark_url_record_state(task_id=42, url_fp="fp-D1", state="done")
    url_hash_d1 = hashlib.sha256(
        "https://example.com/p/1".encode()).hexdigest()
    md.insert_crawl_raw(
        task_id=42, business_context="gov_policy", host="example.com",
        url="https://example.com/p/1", canonical_url="https://example.com/p/1",
        url_hash=url_hash_d1, content_sha256="sha",
        raw_blob_uri="file:///x", data_json="{}",
        etag=None, last_modified=None, run_id="r-prev")
    md.upsert_url_record(
        task_id=42, url_fp="fp-D2", url="https://example.com/p/2",
        host="example.com", depth=1, parent_url_fp="fp-L",
        discovery_source="list_to_detail")
    md.close()

    fetched: list[str] = []
    engine, adapter = _make_engine(
        tmp_path=tmp_path, monkeypatch=monkeypatch, fetched_urls=fetched)
    report = engine.run()
    engine.close()

    assert report.resumed is True
    # 只有 fp-D2 是真正待抓（D1 已在 crawl_raw）
    assert report.urls_resumed == 1
    # 实际 HTTP 只命中 D2
    assert fetched == ["https://example.com/p/2"]
    assert report.detail_urls_fetched == 1
    assert report.raw_records_written == 1
    # adapter.parse_list 不应被调用（列表页已 done，未入队）
    assert adapter.parse_list_calls == []
