"""通用翻页发现 helper（spec: research §3 URL 发现增强）。

为 adapter 提供"非站点专属"的常见翻页模式探测能力。
adapter 可在 parse_list 中调用这些 helper 然后填 ParseListResult.next_pages。

覆盖：
- parse_create_page_html(html): 解析中国政府站常用 createPageHTML(N, cur, prefix, suffix)
  与 createPageHTML(container_id, N, cur, prefix, suffix, rows) 变体
- detect_url_param_paginator(html, base_url): 识别 a[href] 中是否含 ?page=N 模式
- detect_path_paginator(html, base_url): 识别 index_N.html / page/N/ 等路径模式

未覆盖（需 headless / AI）：
- 无限滚动（IntersectionObserver）
- 点击"加载更多"按钮
- 加密 cursor
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse


def parse_create_page_html(html: str) -> tuple[int, str, str] | None:
    """解析 createPageHTML(...) JS 函数调用。

    NDRC、工信部、财政部等多家中国政府站使用 total-first 模式；
    证监会等站点使用 container-id-first 模式。
    返回 (total_pages, prefix, suffix) 或 None。
    """
    pattern = re.compile(
        r"createPageHTML\s*\(\s*"
        r"(?:"
        r"(?P<total>\d+)\s*,\s*\d+\s*,\s*"
        r"['\"](?P<prefix>[^'\"]+)['\"]\s*,\s*"
        r"['\"](?P<suffix>[^'\"]+)['\"]"
        r"|"
        r"['\"][^'\"]+['\"]\s*,\s*"
        r"(?P<total_with_id>\d+)\s*,\s*\d+\s*,\s*"
        r"['\"](?P<prefix_with_id>[^'\"]+)['\"]\s*,\s*"
        r"['\"](?P<suffix_with_id>[^'\"]+)['\"]"
        r")",
    )
    m = pattern.search(html)
    if m:
        total = m.group("total") or m.group("total_with_id")
        prefix = m.group("prefix") or m.group("prefix_with_id")
        suffix = m.group("suffix") or m.group("suffix_with_id")
        if total and prefix and suffix:
            return int(total), prefix, suffix
    return None


def expand_create_page_html_pages(
    list_url: str, total: int, prefix: str, suffix: str,
) -> list[str]:
    """根据 createPageHTML 元数据生成全部翻页 URL（含首页）。

    NDRC 约定：n=0 → prefix.suffix（如 index.html）；n>0 → prefix_n.suffix。
    返回不含当前 list_url 自身的翻页 URL 列表（去重）。
    """
    pages: list[str] = []
    seen: set[str] = set()
    for n in range(total):
        path = f"{prefix}.{suffix}" if n == 0 else f"{prefix}_{n}.{suffix}"
        page_url = urljoin(list_url, path)
        if page_url in seen or page_url == list_url:
            continue
        seen.add(page_url)
        pages.append(page_url)
    return pages


# 常见 query-param 翻页关键词
_COMMON_PAGE_PARAMS = ("page", "pageNum", "pageNo", "pageIndex", "p", "pn")


def detect_url_param_paginator(html: str, base_url: str) -> list[str]:
    """从 HTML 中提取使用 ?page=N 之类参数的翻页链接。

    仅做 DOM 静态发现（不主动探测）；adapter 决定是否生成更多页。
    """
    discovered: list[str] = []
    seen: set[str] = set()
    parsed_base = urlparse(base_url)
    for m in re.finditer(
        r'href="([^"]*?[?&](?:' + "|".join(_COMMON_PAGE_PARAMS) + r')=\d+[^"]*)"',
        html, re.IGNORECASE,
    ):
        absolute = urljoin(base_url, m.group(1))
        # 同 host 才算翻页
        if urlparse(absolute).netloc != parsed_base.netloc:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        discovered.append(absolute)
    return discovered


# 常见 path-based 翻页：index_N.html / list_N.html / page/N/ / pN.html
_PATH_PAGINATOR_PATTERNS = (
    re.compile(r"/(index|list)_\d+\.(html|htm|shtml)$", re.IGNORECASE),
    re.compile(r"/page/\d+/?$", re.IGNORECASE),
    re.compile(r"/p\d+\.(html|htm|shtml)$", re.IGNORECASE),
)


def detect_path_paginator(html: str, base_url: str) -> list[str]:
    """从 HTML 中提取 path-based 翻页 URL。"""
    discovered: list[str] = []
    seen: set[str] = set()
    parsed_base = urlparse(base_url)
    for m in re.finditer(r'href="([^"]+)"', html):
        href = m.group(1)
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != parsed_base.netloc:
            continue
        if not any(p.search(absolute) for p in _PATH_PAGINATOR_PATTERNS):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        discovered.append(absolute)
    return discovered
