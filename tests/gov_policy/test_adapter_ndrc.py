"""T-20260427-107/108 验收：NDRC adapter 解析黄金用例。"""

from __future__ import annotations

from pathlib import Path

from domains.gov_policy import adapters
from domains.gov_policy.adapters import ndrc
from domains.gov_policy.model import SeedSpec
from domains.gov_policy.parse import (
    parse_detail_via_adapter,
    parse_list_via_adapter,
)

GOLDEN_DIR = Path(__file__).parent.parent.parent / "domains/gov_policy/golden/ndrc"


def test_adapter_meta_complete() -> None:
    meta = ndrc.ADAPTER_META
    for key in (
        "host", "schema_version", "data_kind", "supported_modes",
        "list_url_pattern", "detail_url_pattern", "last_verified_at",
        "owner_context",
    ):
        assert key in meta, f"missing ADAPTER_META key: {key}"
    assert meta["host"] == "www.ndrc.gov.cn"
    assert meta["data_kind"] == "policy"
    assert meta["owner_context"] == "gov_policy"


def test_resolve_via_registry() -> None:
    mod = adapters.resolve("www.ndrc.gov.cn")
    assert mod is ndrc
    assert "www.ndrc.gov.cn" in adapters.list_registered()


def test_build_list_url_page0() -> None:
    seed = SeedSpec(
        host="www.ndrc.gov.cn",
        entry_urls=["https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/"],
    )
    assert ndrc.build_list_url(seed, 0) == "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/"


def test_parse_list_extracts_detail_links() -> None:
    """用真实下载的列表页快照验证 parse_list 正确性。"""
    sample = GOLDEN_DIR / "list_page.html"
    if not sample.exists():
        # 测试环境无快照时跳过
        import pytest
        pytest.skip(f"no golden list snapshot at {sample}")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = parse_list_via_adapter(
        "www.ndrc.gov.cn", html,
        "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/",
    )
    assert len(result.detail_links) >= 5, f"expect ≥ 5 detail links, got {len(result.detail_links)}"
    for link in result.detail_links:
        assert link.startswith("https://www.ndrc.gov.cn/xxgk/zcfb/")
        assert link.endswith(".html")


def test_parse_detail_extracts_title_and_body() -> None:
    sample = GOLDEN_DIR / "detail_sample.html"
    if not sample.exists():
        import pytest
        pytest.skip(f"no golden detail snapshot at {sample}")
    html = sample.read_bytes().decode("utf-8", errors="replace")
    result = parse_detail_via_adapter(
        "www.ndrc.gov.cn", html,
        "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202604/t20260409_1404577.html",
    )
    assert result.title, "title should not be empty"
    assert "电力" in result.title or "重大事故" in result.title or len(result.title) > 5
    assert len(result.body_text) > 100, f"body too short: {len(result.body_text)}"
    # 元数据
    meta = result.source_metadata.raw
    assert any(k in meta for k in ("发布时间", "来源")), f"meta should contain at least one common key, got: {meta}"


def test_parse_detail_handles_minimal_html() -> None:
    """边界用例：极简 html 不崩溃。"""
    html = "<html><body><h1>测试政策</h1><div class='article'>正文内容很短</div></body></html>"
    result = parse_detail_via_adapter(
        "www.ndrc.gov.cn", html, "https://www.ndrc.gov.cn/x/y/z.html",
    )
    assert result.title == "测试政策"
    assert "正文内容很短" in result.body_text
