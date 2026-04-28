"""严格去重：联合键 (policy_title_norm, pub_code, content_sha256)。"""

from __future__ import annotations

import re

# 标题规范化：去前后空白、合并内部空白、去首尾标点
_PUNCT_TRIM = re.compile(r"^[【\[（(《\"'\s]+|[】\]）)》\"'\s]+$")
_INTERNAL_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    s = (title or "").strip()
    s = _PUNCT_TRIM.sub("", s)
    s = _INTERNAL_WS.sub(" ", s)
    return s.lower()


def compute_dedup_key(
    *, title: str, pub_code: str | None, content_sha256: str,
) -> tuple[str, str, str]:
    """返回 (title_norm, pub_code_norm, content_sha256) 三元组。"""
    title_norm = normalize_title(title)
    pub_code_norm = (pub_code or "").strip().lower()
    return (title_norm, pub_code_norm, content_sha256)


def is_duplicate(
    a: tuple[str, str, str],
    b: tuple[str, str, str],
) -> bool:
    """三元组完全相等才视为重复。"""
    return a == b
