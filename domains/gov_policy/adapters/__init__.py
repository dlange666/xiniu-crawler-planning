"""站点适配器（每 host 一个文件）。

spec: docs/prod-spec/codegen-output-contract.md §2
"""

from importlib import import_module
from typing import Any

# host → adapter module name 映射
_REGISTRY: dict[str, str] = {
    "www.ndrc.gov.cn": "domains.gov_policy.adapters.ndrc",
}


def resolve(host: str) -> Any:
    """按 host 拿对应 adapter 模块；模块内必须暴露 ADAPTER_META + 3 hook。"""
    mod_name = _REGISTRY.get(host)
    if mod_name is None:
        msg = f"no adapter registered for host: {host!r}"
        raise KeyError(msg)
    return import_module(mod_name)


def list_registered() -> list[str]:
    return sorted(_REGISTRY.keys())
