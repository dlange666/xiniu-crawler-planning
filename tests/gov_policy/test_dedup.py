"""T-20260427-109 验收：联合键严格去重。"""

from __future__ import annotations

from domains.gov_policy.dedup import compute_dedup_key, is_duplicate, normalize_title


def test_normalize_title_trims_punct() -> None:
    assert normalize_title("【某政策办法】") == "某政策办法"
    assert normalize_title("《标题》  ") == "标题"
    assert normalize_title("  Hello   World  ") == "hello world"


def test_dedup_same_pubcode_same_body_is_duplicate() -> None:
    """同 pub_code + 同正文 → 转载关系，应去重。"""
    a = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="abc")
    b = compute_dedup_key(title="【政策 A】", pub_code="国发〔2026〕1号", content_sha256="abc")
    # title 标点不同但规范化后一致；pub_code 一致；正文哈希一致 → 重复
    assert is_duplicate(a, b) is True


def test_dedup_same_pubcode_different_body_kept() -> None:
    """同 pub_code 但正文 sha 不同（修订版）→ 全部保留。"""
    a = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="abc")
    b = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="xyz")
    assert is_duplicate(a, b) is False


def test_dedup_different_pubcode_kept() -> None:
    """pub_code 不同 → 全部保留（不去重）。"""
    a = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕1号", content_sha256="abc")
    b = compute_dedup_key(title="政策 A", pub_code="国发〔2026〕2号", content_sha256="abc")
    assert is_duplicate(a, b) is False


def test_dedup_missing_pubcode_treated_consistently() -> None:
    a = compute_dedup_key(title="政策 A", pub_code=None, content_sha256="abc")
    b = compute_dedup_key(title="政策 A", pub_code="", content_sha256="abc")
    assert is_duplicate(a, b) is True
