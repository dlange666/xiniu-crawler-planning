"""通用解析编排：按 host 路由到 adapters 的 parse_list / parse_detail。"""

from __future__ import annotations

from domains.gov_policy import adapters
from domains.gov_policy.model import ParseDetailResult, ParseListResult


def parse_list_via_adapter(host: str, html: str, url: str) -> ParseListResult:
    adapter = adapters.resolve(host)
    return adapter.parse_list(html, url)


def parse_detail_via_adapter(host: str, html: str, url: str) -> ParseDetailResult:
    adapter = adapters.resolve(host)
    return adapter.parse_detail(html, url)
