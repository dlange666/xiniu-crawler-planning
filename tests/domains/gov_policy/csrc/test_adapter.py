"""CSRC 适配器测试"""

from pathlib import Path

import pytest

from domains.gov_policy.csrc.csrc_adapter import (
    ADAPTER_META,
    build_list_url,
    parse_detail,
    parse_list,
)
from infra.crawl.types import SeedSpec

GOLDEN_DIR = Path(__file__).parent / "fixtures"


def test_adapter_meta():
    """验证 ADAPTER_META 完整性。"""
    assert ADAPTER_META["host"] == "www.csrc.gov.cn"
    assert ADAPTER_META["data_kind"] == "policy"
    assert ADAPTER_META["render_mode"] == "direct"


def test_parse_list():
    """测试 parse_list 提取详情链接。"""
    html_path = GOLDEN_DIR / "csrc_golden_list_1.html"
    html = html_path.read_text(encoding="utf-8", errors="replace")

    url = "http://www.csrc.gov.cn/csrc/c106256/fg.shtml"
    result = parse_list(html, url)

    assert len(result.detail_links) > 0
    assert all("content.shtml" in link for link in result.detail_links)
    assert result.next_pages[:2] == [
        "http://www.csrc.gov.cn/csrc/c106256/fg_1.shtml",
        "http://www.csrc.gov.cn/csrc/c106256/fg_2.shtml",
    ]
    assert result.stop is False


def test_parse_detail():
    """测试 parse_detail 提取标题、正文、metadata。"""
    html_path = GOLDEN_DIR / "csrc_golden_detail_1.html"
    html = html_path.read_text(encoding="utf-8", errors="replace")

    url = "http://www.csrc.gov.cn/csrc/c106256/c3217074/content.shtml"
    result = parse_detail(html, url)

    assert result.title
    assert len(result.body_text) > 100
    assert isinstance(result.source_metadata.raw, dict)
    assert result.source_metadata.raw


def test_build_list_url():
    """测试 build_list_url 入口返回。"""
    seed = SeedSpec(
        host="www.csrc.gov.cn",
        entry_urls=["http://www.csrc.gov.cn/csrc/c106256/fg.shtml"],
        politeness_rps=1.0,
        max_pages_per_run=30,
        crawl_mode="full",
    )

    url = build_list_url(seed, 0)
    assert url == seed.entry_urls[0]

    with pytest.raises(NotImplementedError):
        build_list_url(seed, 1)
