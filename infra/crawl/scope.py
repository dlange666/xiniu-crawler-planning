"""作用域闸口（spec: data-model.md §4.1.1 scope_mode）。

支持 4 种 mode：
- same_origin            : 同 (scheme, host, port)
- same_etld_plus_one     : 同 eTLD+1（MVP 退化为同 host suffix；生产用 publicsuffix2 库）
- url_pattern            : 正则匹配
- allowlist              : host 白名单
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


def _origin(p) -> tuple[str, str, int | None]:  # noqa: ANN001
    return (p.scheme, p.hostname or "", p.port)


def _etld_suffix(host: str) -> str:
    """MVP 简化的 eTLD+1：取最后两段；不处理 .com.cn 等多段后缀。

    生产上应换成 publicsuffix2 / tldextract。
    """
    parts = (host or "").split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def scope_allows(
    *,
    candidate_url: str,
    parent_url: str,
    mode: str,
    url_pattern: str | None = None,
    allowlist_hosts: list[str] | None = None,
) -> tuple[bool, str]:
    """判断 candidate 是否在 task 作用域内。返回 (allowed, reason)。"""
    p_cand = urlparse(candidate_url)
    p_parent = urlparse(parent_url)

    if p_cand.scheme not in ("http", "https"):
        return False, "non-http(s)"

    if mode == "same_origin":
        if _origin(p_cand) == _origin(p_parent):
            return True, "same_origin"
        return False, f"diff origin: {p_cand.netloc} vs {p_parent.netloc}"

    if mode == "same_etld_plus_one":
        cand_etld = _etld_suffix(p_cand.hostname or "")
        parent_etld = _etld_suffix(p_parent.hostname or "")
        if cand_etld == parent_etld:
            return True, f"same_etld_plus_one: {cand_etld}"
        return False, f"diff etld: {cand_etld} vs {parent_etld}"

    if mode == "url_pattern":
        if not url_pattern:
            return False, "url_pattern mode requires scope_url_pattern"
        if re.match(url_pattern, candidate_url):
            return True, "matches pattern"
        return False, f"no match: {url_pattern}"

    if mode == "allowlist":
        if not allowlist_hosts:
            return False, "allowlist mode requires scope_allowlist_hosts"
        host = p_cand.hostname or ""
        if host in allowlist_hosts:
            return True, "host in allowlist"
        return False, f"host {host!r} not in allowlist"

    return False, f"unknown mode: {mode}"
