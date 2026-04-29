"""SASAC adapter 验收：黄金用例 + ADAPTER_META 完整性。"""

from __future__ import annotations

from pathlib import Path

import pytest

from domains.gov_policy.sasac import sasac_adapter as sasac
from infra import adapter_registry
from infra.crawl import SeedSpec

SASAC_DIR = Path(__file__).parent.parent.parent / "domains/gov_policy/sasac"


def test_adapter_meta_complete() -> None:
    meta = sasac.ADAPTER_META
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
    assert meta["host"] == "www.sasac.gov.cn"
    assert meta["data_kind"] == "policy"
    assert meta["owner_context"] == "gov_policy"


def test_resolve_via_registry() -> None:
    adapter_registry.reset()
    adapter_registry.discover()
    entry = adapter_registry.get("gov_policy", "www.sasac.gov.cn")
    assert entry.module_path == "domains.gov_policy.sasac.sasac_adapter"
    assert entry.module.ADAPTER_META["host"] == "www.sasac.gov.cn"
    assert "www.sasac.gov.cn" in {e.host for e in adapter_registry.list_all()}


def test_build_list_url_page0() -> None:
    seed = SeedSpec(
        host="www.sasac.gov.cn",
        entry_urls=["http://www.sasac.gov.cn/n2588035/n2588320/n2588335/index.html"],
    )
    url = sasac.build_list_url(seed, 0)
    assert url == "http://www.sasac.gov.cn/n2588035/n2588320/n2588335/index.html"


def test_parse_list_extracts_detail_links() -> None:
    sample = SASAC_DIR / "sasac_golden_list_1.html"
    if not sample.exists():
        pytest.skip(f"no golden list snapshot at {sample}")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = sasac.parse_list(html, "http://www.sasac.gov.cn/n2588035/n2588320/n2588335/index.html")
    assert len(result.detail_links) >= 5, f"expect ≥ 5 detail links, got {len(result.detail_links)}"
    for link in result.detail_links:
        assert "sasac.gov.cn" in link
        assert link.endswith(".html")
        assert "/n2588035/n2588320/n2588335/" in link


def test_parse_list_emits_pagination() -> None:
    sample = SASAC_DIR / "sasac_golden_list_1.html"
    if not sample.exists():
        pytest.skip("no golden list snapshot")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = sasac.parse_list(html, "http://www.sasac.gov.cn/n2588035/n2588320/n2588335/index.html")
    assert len(result.next_pages) >= 2, f"expect ≥ 2 paginated URLs, got {len(result.next_pages)}"
    urls = result.next_pages
    assert any("index_2603340_" in u for u in urls)


def test_parse_detail_extracts_title_and_body() -> None:
    sample = SASAC_DIR / "sasac_golden_detail_1.html"
    if not sample.exists():
        pytest.skip("no golden detail snapshot")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = sasac.parse_detail(
        html,
        "http://www.sasac.gov.cn/n2588035/n2588320/n2588335/c35128064/content.html",
    )
    assert result.title, "title should not be empty"
    assert "中央企业" in result.title or len(result.title) > 5
    assert len(result.body_text) > 100, f"body too short: {len(result.body_text)}"
    assert "var contenttitle" not in result.body_text
    assert "var shareDes" not in result.body_text
    meta = result.source_metadata.raw
    assert any(k in meta for k in ("发布机关", "发布日期", "content_id")), (
        f"meta should contain at least one common key, got: {meta}"
    )


def test_parse_detail_handles_minimal_html() -> None:
    html = "<html><body><h1>测试政策</h1></body></html>"
    result = sasac.parse_detail(html, "http://www.sasac.gov.cn/x/y/z.html")
    assert "测试政策" in result.title
