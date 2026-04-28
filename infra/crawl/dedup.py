"""解析层严格去重（spec: data-model.md §4.2.3 + architecture.md §5）。

联合键：(policy_title_norm, pub_code, content_sha256) 一致才去重；不一致全保留。
simhash 仅作信号（暂缓，TD-003）。

业务无关：MVP 阶段所有业务域用同一键定义；如未来某业务需自定义键，
该业务的 spec 应明确字段映射（如 exchange_policy 的 announcement_no 等价 pub_code）。
"""

from __future__ import annotations

import re

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
    """返回 (title_norm, pub_code_norm, content_sha256) 联合键。"""
    title_norm = normalize_title(title)
    pub_code_norm = (pub_code or "").strip().lower()
    return (title_norm, pub_code_norm, content_sha256)


def is_duplicate(
    a: tuple[str, str, str],
    b: tuple[str, str, str],
) -> bool:
    return a == b
