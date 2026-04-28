"""Adapter 注册中心：声明式自动发现 (business_context, host) → adapter。

spec: docs/prod-spec/codegen-output-contract.md §2

使用方式：
    from infra.adapter_registry import discover, get, list_all

    discover()                                  # 启动时调一次
    entry = get("gov_policy", "www.ndrc.gov.cn")
    entry.module.parse_list(html, url)
"""

from __future__ import annotations

from .errors import AdapterNotFound, DuplicateAdapter, InvalidAdapterMeta
from .registry import (
    AdapterEntry,
    discover,
    get,
    list_all,
    resolve_by_url,
    reset,
)

__all__ = [
    "AdapterEntry",
    "AdapterNotFound",
    "DuplicateAdapter",
    "InvalidAdapterMeta",
    "discover",
    "get",
    "list_all",
    "reset",
    "resolve_by_url",
]
