from __future__ import annotations

import json
from pathlib import Path

from infra.source_probe import ProbeFetchResult, SourceProbe


class FakeFetcher:
    def __init__(self, mapping: dict[str, ProbeFetchResult]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def __call__(self, url: str, host: str) -> ProbeFetchResult:
        self.calls.append(url)
        return self.mapping[url]


def _resp(
    url: str,
    body: bytes,
    *,
    content_type: str = "text/html; charset=utf-8",
    status_code: int = 200,
    anti_bot_signal: str | None = None,
) -> ProbeFetchResult:
    return ProbeFetchResult(
        url=url,
        final_url=url,
        status_code=status_code,
        headers={"content-type": content_type},
        body=body,
        anti_bot_signal=anti_bot_signal,
    )


def test_probe_detects_json_candidate_and_writes_artifacts(tmp_path: Path) -> None:
    entry_url = "https://www.gov.cn/yaowen/liebiao/"
    json_url = "https://www.gov.cn/yaowen/liebiao/YAOWENLIEBIAO.json"
    html = b"""
    <html><body>
      <ul id="list-1-ajax-id"></ul>
      <script>$.ajax({url: "./YAOWENLIEBIAO.json"});</script>
    </body></html>
    """
    fetcher = FakeFetcher(
        {
            entry_url: _resp(entry_url, html),
            json_url: _resp(
                json_url,
                b'[{"TITLE":"x","URL":"https://www.gov.cn/yaowen/liebiao/202604/content.htm"}]',
                content_type="application/json",
            ),
        }
    )
    probe = SourceProbe(fetch=fetcher, robots_allowed=lambda url: (True, "ok"))

    result = probe.probe(url=entry_url, host="www.gov.cn", out_dir=tmp_path)

    assert result.verdict == "json_api"
    assert result.recommended_source_url == json_url
    assert [Path(a.path).name for a in result.artifacts] == [
        "entry.html",
        "json-candidate-1.json",
    ]
    saved = json.loads((tmp_path / "probe-result.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "json_api"


def test_probe_follows_javascript_redirect_before_json_detection(tmp_path: Path) -> None:
    entry_url = "https://www.gov.cn/yaowen/"
    redirected_url = "https://www.gov.cn/yaowen/liebiao/"
    json_url = "https://www.gov.cn/yaowen/liebiao/YAOWENLIEBIAO.json"
    fetcher = FakeFetcher(
        {
            entry_url: _resp(
                entry_url,
                b'<script>window.location.href="https://www.gov.cn/yaowen/liebiao/";</script>',
            ),
            redirected_url: _resp(
                redirected_url,
                b'<script>$.ajax({url: "./YAOWENLIEBIAO.json"});</script>',
            ),
            json_url: _resp(json_url, b'[{"TITLE":"x"}]', content_type="application/json"),
        }
    )
    probe = SourceProbe(fetch=fetcher, robots_allowed=lambda url: (True, "ok"))

    result = probe.probe(url=entry_url, host="www.gov.cn", out_dir=tmp_path)

    assert result.verdict == "json_api"
    assert result.final_url == redirected_url
    assert result.recommended_source_url == json_url
    assert "js_redirect:https://www.gov.cn/yaowen/liebiao/" in result.signals


def test_probe_marks_js_shell_as_headless_required(tmp_path: Path) -> None:
    entry_url = "https://flk.npc.gov.cn/index"
    fetcher = FakeFetcher(
        {
            entry_url: _resp(
                entry_url,
                b"""<html><head><script src="/assets/index.js"></script></head>
                <body><div id="app"></div></body></html>""",
            )
        }
    )
    probe = SourceProbe(fetch=fetcher, robots_allowed=lambda url: (True, "ok"))

    result = probe.probe(url=entry_url, host="flk.npc.gov.cn", out_dir=tmp_path)

    assert result.verdict == "headless_required"
    assert result.render_required is True
    assert "js_shell_detected" in result.signals


def test_probe_stops_on_robots_disallow(tmp_path: Path) -> None:
    fetcher = FakeFetcher({})
    probe = SourceProbe(fetch=fetcher, robots_allowed=lambda url: (False, "status=500"))

    result = probe.probe(url="https://example.com/", host="example.com", out_dir=tmp_path)

    assert result.verdict == "robots_disallow"
    assert result.blocked_reason == "status=500"
    assert fetcher.calls == []
