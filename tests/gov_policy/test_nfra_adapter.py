"""NFRA adapter 验收：黄金用例 + ADAPTER_META 完整性。"""

from __future__ import annotations

from pathlib import Path

import pytest

from domains.gov_policy.nfra import nfra_adapter as nfra
from infra import adapter_registry
from infra.crawl import SeedSpec

NFRA_DIR = Path(__file__).parent.parent.parent / "domains/gov_policy/nfra"


def test_adapter_meta_complete() -> None:
    meta = nfra.ADAPTER_META
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
    assert meta["host"] == "www.nfra.gov.cn"
    assert meta["data_kind"] == "policy"
    assert meta["owner_context"] == "gov_policy"


def test_resolve_via_registry() -> None:
    adapter_registry.reset()
    adapter_registry.discover()
    entry = adapter_registry.get("gov_policy", "www.nfra.gov.cn")
    assert entry.module_path == "domains.gov_policy.nfra.nfra_adapter"
    assert entry.module.ADAPTER_META["host"] == "www.nfra.gov.cn"
    assert "www.nfra.gov.cn" in {e.host for e in adapter_registry.list_all()}


def test_build_list_url_page0() -> None:
    seed = SeedSpec(
        host="www.nfra.gov.cn",
        entry_urls=[
            "https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild/data_itemId=861,pageIndex=1,pageSize=18.json"
        ],
    )
    url = nfra.build_list_url(seed, 0)
    assert "SelectDocByItemIdAndChild" in url
    assert "pageIndex=1" in url


def test_parse_list_extracts_detail_links() -> None:
    sample = NFRA_DIR / "nfra_golden_list_001.html"
    if not sample.exists():
        pytest.skip(f"no golden list snapshot at {sample}")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = nfra.parse_list(html, "https://www.nfra.gov.cn/cbircweb/solr/openGovSerch?pageNo=2")
    assert len(result.detail_links) >= 5, f"expect ≥ 5 detail links, got {len(result.detail_links)}"
    for link in result.detail_links:
        assert "SelectByDocId" in link
        assert "docId=" in link


def test_parse_list_emits_pagination() -> None:
    sample = NFRA_DIR / "nfra_golden_list_001.html"
    if not sample.exists():
        pytest.skip("no golden list snapshot")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = nfra.parse_list(html, "https://www.nfra.gov.cn/cbircweb/solr/openGovSerch?pageNo=2")
    assert len(result.next_pages) >= 1, f"expect ≥ 1 pagination, got {len(result.next_pages)}"


def test_parse_detail_extracts_title_and_body() -> None:
    sample = NFRA_DIR / "nfra_golden_detail_001.html"
    if not sample.exists():
        pytest.skip("no golden detail snapshot")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = nfra.parse_detail(
        html,
        "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectByDocId?docId=1255850",
    )
    assert result.title, "title should not be empty"
    assert len(result.body_text) > 10, f"body too short: {len(result.body_text)}"
    meta = result.source_metadata.raw
    assert any(k in meta for k in ("publishDate", "indexNo", "docSource")), (
        f"meta should contain at least one common key, got: {meta}"
    )


def test_parse_detail_extracts_attachments() -> None:
    sample = NFRA_DIR / "nfra_golden_detail_001.html"
    if not sample.exists():
        pytest.skip("no golden detail snapshot")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = nfra.parse_detail(
        html,
        "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectByDocId?docId=1255850",
    )
    assert isinstance(result.attachments, list)


def test_parse_detail_extracts_interpret_links() -> None:
    sample = NFRA_DIR / "nfra_golden_detail_001.html"
    if not sample.exists():
        pytest.skip("no golden detail snapshot")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = nfra.parse_detail(
        html,
        "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectByDocId?docId=1255850",
    )
    assert isinstance(result.interpret_links, list)
