"""全局 adapter 注册表。

线程安全考量：MVP 单进程，启动时调一次 discover() 即冻结；
get() / list_all() 是只读，无需锁。
"""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path

from .errors import AdapterNotFound, DuplicateAdapter
from .meta import AdapterEntry, build_entry

logger = logging.getLogger(__name__)

_REGISTRY: dict[tuple[str, str], AdapterEntry] = {}
_DISCOVERED: bool = False


def reset() -> None:
    """清空注册表。仅供测试。"""
    global _DISCOVERED
    _REGISTRY.clear()
    _DISCOVERED = False


def discover(*, domains_root: Path | None = None) -> int:
    """扫描 domains/*/adapters/*.py，凡含 ADAPTER_META 的模块自动登记。

    幂等：重复调用不会重注册（按 module_path 去重），但会刷新 _DISCOVERED 标记。
    返回新增条目数。
    """
    global _DISCOVERED
    root = domains_root or _default_domains_root()
    if not root.is_dir():
        logger.warning("adapter discovery: %s not found, skip", root)
        _DISCOVERED = True
        return 0

    added = 0
    for ctx_dir in sorted(root.iterdir()):
        if not ctx_dir.is_dir() or ctx_dir.name.startswith("_"):
            continue
        adapters_dir = ctx_dir / "adapters"
        if not adapters_dir.is_dir():
            continue
        for py_file in sorted(adapters_dir.glob("*.py")):
            if py_file.stem.startswith("_"):
                continue
            module_path = f"domains.{ctx_dir.name}.adapters.{py_file.stem}"
            module = import_module(module_path)
            if not hasattr(module, "ADAPTER_META"):
                continue
            entry = build_entry(
                module=module,
                module_path=module_path,
                inferred_business_context=ctx_dir.name,
            )
            _register(entry)
            added += 1

    _DISCOVERED = True
    logger.info(
        "adapter discovery done: %d entries (%s)",
        len(_REGISTRY),
        ", ".join(f"{ctx}/{host}" for (ctx, host) in sorted(_REGISTRY.keys())),
    )
    return added


def _register(entry: AdapterEntry) -> None:
    key = (entry.business_context, entry.host)
    existing = _REGISTRY.get(key)
    if existing is not None:
        if existing.module_path == entry.module_path:
            # 同模块重复 import（discover 被多调）→ 静默忽略
            return
        msg = (
            f"duplicate adapter for ({entry.business_context}, {entry.host}): "
            f"{existing.module_path} vs {entry.module_path}"
        )
        raise DuplicateAdapter(msg)
    _REGISTRY[key] = entry


def get(business_context: str, host: str) -> AdapterEntry:
    """主调用入口。未注册抛 AdapterNotFound（含候选列表）。"""
    key = (business_context, host)
    entry = _REGISTRY.get(key)
    if entry is None:
        candidates = sorted(
            f"{ctx}/{h}" for (ctx, h) in _REGISTRY.keys()
            if ctx == business_context
        )
        hint = (
            f" (registered hosts in {business_context}: {candidates})"
            if candidates else " (no adapters registered for this context)"
        )
        msg = f"no adapter registered for ({business_context}, {host}){hint}"
        raise AdapterNotFound(msg)
    return entry


def list_all(*, business_context: str | None = None) -> list[AdapterEntry]:
    """列出全部已注册 adapter；可按业务域过滤。"""
    items = list(_REGISTRY.values())
    if business_context is not None:
        items = [e for e in items if e.business_context == business_context]
    return sorted(items, key=lambda e: (e.business_context, e.host))


def resolve_by_url(url: str, business_context: str) -> AdapterEntry | None:
    """按 list_url_pattern / detail_url_pattern 反查 adapter；不匹配返回 None。

    供递归发现时判定 URL 类型用（详情/列表），多匹配时返回第一个。
    """
    for entry in list_all(business_context=business_context):
        if entry.list_url_pattern.match(url) or entry.detail_url_pattern.match(url):
            return entry
    return None


def _default_domains_root() -> Path:
    # registry.py 位于 infra/adapter_registry/，仓库根 = parents[2]
    return Path(__file__).resolve().parents[2] / "domains"
