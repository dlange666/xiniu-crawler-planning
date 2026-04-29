from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from infra.crawl import CrawlEngine
from infra.crawl.types import ParseDetailResult, ParseListResult, SeedSpec, TaskSpec
from infra.render import RenderConfig, RendererPool, RenderRequest
from infra.render.types import RenderResult


class _RenderAdapter:
    ADAPTER_META = {
        "host": "example.com",
        "schema_version": 1,
        "render_mode": "direct",
    }

    def parse_list(self, html: str, base_url: str) -> ParseListResult:
        return ParseListResult(detail_links=["https://example.com/detail"])

    def parse_detail(self, html: str, base_url: str) -> ParseDetailResult:
        if "rendered-body" not in html:
            raise ValueError("missing rendered body")
        return ParseDetailResult(title="rendered", body_text="rendered-body")

    def should_render(self, html: str, url: str) -> bool:
        return "id='app'" in html


class _FakeResp:
    def __init__(self, url: str, body: bytes) -> None:
        self.status_code = 200
        self.body = body
        self.final_url = url
        self.headers = {"content-type": "text/html"}
        self.elapsed_ms = 1
        self.error_kind = None
        self.error_detail = None
        self.anti_bot_signal = None


class _FakeRenderBackend:
    def render(self, request: RenderRequest) -> RenderResult:
        return RenderResult(
            url=request.url,
            final_url=request.url,
            status_code=200,
            html="<html><body>rendered-body</body></html>",
            elapsed_ms=2,
            bytes_received=39,
        )


def test_crawl_engine_uses_injected_renderer_for_adapter_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_PROFILE", "dev")
    monkeypatch.setenv("CRAWLER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CRAWLER_BLOB_ROOT", str(tmp_path / "blobs"))

    adapter = _RenderAdapter()
    engine = CrawlEngine(
        task=TaskSpec(task_id=9, max_depth=1, scope_mode="same_origin"),
        seed=SeedSpec(host="example.com", entry_urls=["https://example.com/list"]),
        adapter_resolver=lambda host: adapter,
        renderer=RendererPool(
            backend=_FakeRenderBackend(),
            config=RenderConfig(enabled=True),
        ),
    )
    engine.robots.is_allowed = lambda url: (True, "ok")  # type: ignore[method-assign]

    def fake_fetch(url: str, *, host: str = "", **kwargs: Any) -> _FakeResp:
        if url.endswith("/list"):
            return _FakeResp(url, b"<a href='/detail'>detail</a>")
        return _FakeResp(url, b"<div id='app'></div>")

    engine.http.fetch = fake_fetch  # type: ignore[method-assign]

    report = engine.run()

    rows = engine.metadata.fetch_all(
        "SELECT rendered FROM fetch_record ORDER BY fetch_id",
    )
    payload = json.loads(engine.metadata.fetch_one(
        "SELECT data FROM crawl_raw WHERE task_id=9",
    )[0])
    engine.close()

    assert report.raw_records_written == 1
    assert rows[-1] == (1,)
    assert payload["rendered"] is True
