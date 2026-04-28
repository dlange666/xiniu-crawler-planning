"""infra/crawl/scope 4 种 mode 单元测试。"""

from __future__ import annotations

from infra.crawl import scope_allows


def test_same_origin() -> None:
    ok, _ = scope_allows(
        candidate_url="https://x.com/a/b",
        parent_url="https://x.com/c", mode="same_origin")
    assert ok is True
    ok, _ = scope_allows(
        candidate_url="https://other.com/a",
        parent_url="https://x.com/c", mode="same_origin")
    assert ok is False
    # 不同 scheme
    ok, _ = scope_allows(
        candidate_url="http://x.com/a",
        parent_url="https://x.com/c", mode="same_origin")
    assert ok is False


def test_etld_plus_one() -> None:
    ok, _ = scope_allows(
        candidate_url="https://wap.miit.gov.cn/a",
        parent_url="https://www.miit.gov.cn/b", mode="same_etld_plus_one")
    assert ok is True
    ok, _ = scope_allows(
        candidate_url="https://other.org/x",
        parent_url="https://www.miit.gov.cn/b", mode="same_etld_plus_one")
    assert ok is False


def test_url_pattern() -> None:
    pattern = r"^https?://www\.ndrc\.gov\.cn/xxgk/(zcfb|jd)/.*"
    ok, _ = scope_allows(
        candidate_url="https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/x.html",
        parent_url="https://www.ndrc.gov.cn/", mode="url_pattern",
        url_pattern=pattern)
    assert ok is True
    ok, _ = scope_allows(
        candidate_url="https://www.ndrc.gov.cn/other/path",
        parent_url="https://www.ndrc.gov.cn/", mode="url_pattern",
        url_pattern=pattern)
    assert ok is False


def test_allowlist() -> None:
    hosts = ["www.ndrc.gov.cn", "wap.miit.gov.cn"]
    ok, _ = scope_allows(
        candidate_url="https://www.ndrc.gov.cn/x",
        parent_url="https://x.com/", mode="allowlist",
        allowlist_hosts=hosts)
    assert ok is True
    ok, _ = scope_allows(
        candidate_url="https://other.com/x",
        parent_url="https://x.com/", mode="allowlist",
        allowlist_hosts=hosts)
    assert ok is False


def test_non_http_rejected() -> None:
    ok, _ = scope_allows(
        candidate_url="javascript:alert(1)",
        parent_url="https://x.com/", mode="same_origin")
    assert ok is False
    ok, _ = scope_allows(
        candidate_url="ftp://x.com/file",
        parent_url="https://x.com/", mode="same_origin")
    assert ok is False
