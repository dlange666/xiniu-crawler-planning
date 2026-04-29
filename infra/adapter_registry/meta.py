"""ADAPTER_META 校验与 AdapterEntry 构建。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from types import ModuleType
from typing import Any

from .errors import InvalidAdapterMeta

REQUIRED_KEYS: tuple[str, ...] = (
    "host",
    "schema_version",
    "data_kind",
    "list_url_pattern",
    "detail_url_pattern",
    "last_verified_at",
)
REQUIRED_HOOKS: tuple[str, ...] = ("parse_list", "parse_detail")

VALID_RENDER_MODES: frozenset[str] = frozenset({"direct", "headless"})


@dataclass(frozen=True)
class AdapterEntry:
    """注册表单元。frozen=True：注册后不可变。"""

    business_context: str
    host: str
    schema_version: int
    data_kind: str
    list_url_pattern: re.Pattern[str]
    detail_url_pattern: re.Pattern[str]
    last_verified_at: date
    module: ModuleType
    module_path: str         # "domains.gov_policy.ndrc.ndrc_adapter"，排错用
    supported_modes: tuple[str, ...] = ("full",)
    # 渲染策略：direct=httpx 直连（默认）；headless=Playwright（暂未实现）
    # 触发 headless 的条件见 architecture.md §5 "抓取层级顺序"
    render_mode: str = "direct"


def build_entry(
    *,
    module: ModuleType,
    module_path: str,
    inferred_business_context: str,
) -> AdapterEntry:
    """读取 module.ADAPTER_META，校验并构建 AdapterEntry。

    business_context 优先用 META 显式声明的 owner_context；
    否则回退到从模块路径推断（domains.<ctx>.<source>.<source>_adapter）。
    """
    meta: dict[str, Any] | None = getattr(module, "ADAPTER_META", None)
    if not isinstance(meta, dict):
        msg = (
            f"adapter {module_path} missing ADAPTER_META (or not a dict); "
            "see codegen-output-contract.md §2"
        )
        raise InvalidAdapterMeta(msg)

    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        msg = f"adapter {module_path} ADAPTER_META missing keys: {missing}"
        raise InvalidAdapterMeta(msg)

    for hook in REQUIRED_HOOKS:
        fn = getattr(module, hook, None)
        if not callable(fn):
            msg = f"adapter {module_path} missing callable hook: {hook}()"
            raise InvalidAdapterMeta(msg)

    try:
        list_re = re.compile(meta["list_url_pattern"])
        detail_re = re.compile(meta["detail_url_pattern"])
    except re.error as e:
        msg = f"adapter {module_path} url pattern compile failed: {e}"
        raise InvalidAdapterMeta(msg) from e

    last_verified = _coerce_date(meta["last_verified_at"], module_path)
    schema_version = _coerce_int(meta["schema_version"], "schema_version", module_path)

    business_context = (
        meta.get("owner_context")
        or meta.get("business_context")
        or inferred_business_context
    )
    if not isinstance(business_context, str) or not business_context:
        msg = (
            f"adapter {module_path}: cannot determine business_context "
            "(neither META.owner_context nor module path supplied one)"
        )
        raise InvalidAdapterMeta(msg)

    host = meta["host"]
    if not isinstance(host, str) or not host:
        msg = f"adapter {module_path}: META.host must be non-empty string"
        raise InvalidAdapterMeta(msg)

    supported = meta.get("supported_modes", ("full",))
    if isinstance(supported, list):
        supported = tuple(supported)

    render_mode = meta.get("render_mode", "direct")
    if render_mode not in VALID_RENDER_MODES:
        msg = (
            f"adapter {module_path}: META.render_mode={render_mode!r} "
            f"not in {sorted(VALID_RENDER_MODES)}"
        )
        raise InvalidAdapterMeta(msg)

    return AdapterEntry(
        business_context=business_context,
        host=host,
        schema_version=schema_version,
        data_kind=str(meta["data_kind"]),
        list_url_pattern=list_re,
        detail_url_pattern=detail_re,
        last_verified_at=last_verified,
        module=module,
        module_path=module_path,
        supported_modes=tuple(supported),
        render_mode=render_mode,
    )


def _coerce_int(v: Any, key: str, module_path: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        msg = f"adapter {module_path}: META.{key} must be int (got {type(v).__name__})"
        raise InvalidAdapterMeta(msg)
    return v


def _coerce_date(v: Any, module_path: str) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError as e:
            msg = (
                f"adapter {module_path}: META.last_verified_at "
                f"must be ISO date (YYYY-MM-DD); got {v!r}"
            )
            raise InvalidAdapterMeta(msg) from e
    msg = (
        f"adapter {module_path}: META.last_verified_at must be date or "
        f"ISO string; got {type(v).__name__}"
    )
    raise InvalidAdapterMeta(msg)
