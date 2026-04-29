"""infra/crawl/dedup 严格去重测试。"""

from __future__ import annotations

from infra.crawl import compute_dedup_key, is_duplicate, normalize_title


def test_normalize_title_trims_punct() -> None:
    assert normalize_title("【某政策办法】") == "某政策办法"
    assert normalize_title("《标题》  ") == "标题"
    assert normalize_title("  Hello   World  ") == "hello world"


def test_dedup_same_pubcode_same_body_is_duplicate() -> None:
    a = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="abc")
    b = compute_dedup_key(title="【政策 A】", pub_code="国发〔2026〕1号", content_sha256="abc")
    assert is_duplicate(a, b) is True


def test_dedup_same_pubcode_different_body_kept() -> None:
    a = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="abc")
    b = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="xyz")
    assert is_duplicate(a, b) is False


def test_dedup_different_pubcode_kept() -> None:
    a = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="abc")
    b = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕2号", content_sha256="abc")
    assert is_duplicate(a, b) is False


def test_dedup_missing_pubcode_treated_consistently() -> None:
    a = compute_dedup_key(title="政策 A", pub_code=None, content_sha256="abc")
    b = compute_dedup_key(title="政策 A", pub_code="", content_sha256="abc")
    assert is_duplicate(a, b) is True
