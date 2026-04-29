"""MOST adapter 验收：golden 用例 + ADAPTER_META 注册。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domains.gov_policy.most import most_adapter as most
from infra import adapter_registry
from infra.crawl import SeedSpec

GOLDEN_DIR = Path(__file__).parent / "fixtures"
LIST_HTML = GOLDEN_DIR / "most_golden_list_page.html"
LIST_EXPECT = GOLDEN_DIR / "most_golden_list_page.golden.json"
DETAIL_CASES = sorted(GOLDEN_DIR.glob("most_golden_detail_*.golden.json"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_adapter_meta_complete() -> None:
    meta = most.ADAPTER_META
    for key in (
        "host",
        "schema_version",
        "data_kind",
        "supported_modes",
        "list_url_pattern",
        "detail_url_pattern",
        "last_verified_at",
        "owner_context",
    ):
        assert key in meta, f"missing ADAPTER_META key: {key}"
    assert meta["host"] == "www.most.gov.cn"
    assert meta["data_kind"] == "policy"
    assert meta["owner_context"] == "gov_policy"
    assert meta["render_mode"] == "direct"


def test_resolve_via_registry() -> None:
    adapter_registry.reset()
    adapter_registry.discover()
    entry = adapter_registry.get("gov_policy", "www.most.gov.cn")
    assert entry.module is most
    assert entry.module_path == "domains.gov_policy.most.most_adapter"
    assert entry.render_mode == "direct"


def test_build_list_url_page0() -> None:
    seed = SeedSpec(
        host="www.most.gov.cn",
        entry_urls=["https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/"],
    )
    assert most.build_list_url(seed, 0) == seed.entry_urls[0]


def test_parse_list_extracts_main_policy_links_only() -> None:
    expect = _load_json(LIST_EXPECT)
    html = LIST_HTML.read_text(encoding="utf-8", errors="replace")
    result = most.parse_list(html, expect["url"])

    assert len(result.detail_links) >= expect["expected_min_detail_links"]
    assert result.stop is True
    assert result.next_pages == []
    for link in result.detail_links:
        assert link.startswith("https://www.most.gov.cn/")
        assert link.endswith(".html")
        assert any(path in link for path in expect["expected_paths"])
        assert not any(path in link for path in expect["excluded_paths"])


@pytest.mark.parametrize("golden_json", DETAIL_CASES, ids=lambda p: p.stem)
def test_parse_detail_against_golden(golden_json: Path) -> None:
    expect = _load_json(golden_json)
    html_path = GOLDEN_DIR / golden_json.name.replace(".golden.json", ".html")
    html = html_path.read_text(encoding="utf-8", errors="replace")

    result = most.parse_detail(html, expect["url"])

    assert expect["title_contains"] in result.title
    assert len(result.body_text) >= expect["min_body_len"]
    assert len(result.interpret_links) >= expect["expected_min_interpret_links"]
    metadata = result.source_metadata.raw
    for key, value in expect["required_metadata"].items():
        assert metadata.get(key) == value


def test_parse_detail_handles_minimal_html() -> None:
    html = "<html><body><h1>测试政策</h1><div id='Zoom'>正文内容很短</div></body></html>"
    result = most.parse_detail(html, "https://www.most.gov.cn/x/y/z.html")
    assert result.title == "测试政策"
    assert "正文内容很短" in result.body_text
