"""通用解析编排器：调度对应 adapter 的 hook。"""

from .orchestrator import parse_detail_via_adapter, parse_list_via_adapter

__all__ = ["parse_detail_via_adapter", "parse_list_via_adapter"]
