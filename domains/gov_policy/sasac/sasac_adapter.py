"""国务院国有资产监督管理委员会 (www.sasac.gov.cn) 政策文件库适配器。

入口：http://www.sasac.gov.cn/n2588035/n2588320/index.html

spec: docs/prod-spec/codegen-output-contract.md §2 (ADAPTER_META + hook 协议)
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from infra.crawl.pagination_helpers import (
    expand_create_page_html_pages,
    parse_create_page_html,
)
from infra.crawl.types import (
    ParseDetailResult,
    ParseListResult,
    SeedSpec,
    SourceMetadata,
)

ADAPTER_META: dict = {
    "host": "www.sasac.gov.cn",
    "schema_version": 1,
    "data_kind": "policy",
    "supported_modes": ["full"],
    "render_mode": "direct",
    "list_url_pattern": r"^https?://www\.sasac\.gov\.cn/n2588035/n2588320/.*",
    "detail_url_pattern": r"^https?://www\.sasac\.gov\.cn/n2588035/n2588320/n2588335/c\d+/content\.html$",
    "last_verified_at": "2026-04-29",
    "owner_context": "gov_policy",
}

_POLICY_DETAIL_LINK_RE = re.compile(r"/n2588035/n2588320/n2588335/c\d+/content\.html$")


def build_list_url(seed: SeedSpec, page: int) -> str:
    """构造列表页 URL。仅 page=0 强约束；翻页由 parse_list 自己暴露给引擎。"""
    if not seed.entry_urls:
        msg = "seed.entry_urls is empty"
        raise ValueError(msg)
    if page == 0:
        return seed.entry_urls[0]
    msg = f"sasac adapter: pagination is parsed dynamically, not by build_list_url(page={page})"
    raise NotImplementedError(msg)


def parse_list(html: str, url: str) -> ParseListResult:
    """解析列表页：提详情链接 + 探翻页。"""
    soup = BeautifulSoup(html, "lxml")

    detail_links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        absolute = urljoin(url, a["href"])
        if not _POLICY_DETAIL_LINK_RE.search(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        detail_links.append(absolute)

    next_pages: list[str] = []
    cph = parse_create_page_html(html)
    if cph is not None:
        total, prefix, suffix = cph
        next_pages = expand_create_page_html_pages(url, total, prefix, suffix)

    if not next_pages:
        hidden_links = soup.find("div", style=lambda x: x and "display:none" in x)
        if hidden_links:
            for a in hidden_links.find_all("a", href=True):
                href = a["href"]
                if "index_2603340_" in href:
                    abs_url = urljoin(url, href)
                    next_pages.append(abs_url)

    def _page_number(page_url: str) -> int:
        match = re.search(r"index_\d+_(\d+)\.html$", page_url)
        if match:
            return int(match.group(1))
        return 0

    next_pages = sorted(set(next_pages), key=_page_number)

    return ParseListResult(
        detail_links=detail_links,
        next_pages=next_pages,
        next_page=None,
        stop=False,
    )


_META_LABEL_KEYS = (
    "发布机关",
    "发文机关",
    "发文字号",
    "主题分类",
    "成文日期",
    "发布时期",
    "索引号",
)


def _extract_metadata_from_script(soup: BeautifulSoup, url: str) -> dict[str, str]:
    meta: dict[str, str] = {}

    for meta_tag in soup.find_all("meta"):
        name = meta_tag.get("name", "")
        content = meta_tag.get("content", "")
        if name == "liability":
            meta["发布机关"] = content
        elif name == "publishdate":
            meta["发布日期"] = content
        elif name == "contentid":
            meta["content_id"] = content

    scripts = soup.find_all("script")
    for script in scripts:
        text = script.string or ""
        if "var contenttitle" in text:
            m = re.search(r'var\s+contenttitle\s*=\s*[`"]([^`"]+)[`"]', text)
            if m:
                meta["title_from_script"] = m.group(1).strip()
            m = re.search(r'getAttrByFlatName\([\'"](\w+)[\'"]\)', text)
            if m:
                meta["source_attr"] = m.group(1)

    return meta


def parse_detail(html: str, url: str) -> ParseDetailResult:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            raw = t.get_text(strip=True)
            title = re.sub(r"-国务院国有资产监督管理委员会\s*$", "", raw)
            title = re.sub(r"^[【\[]\s*|\s*[】\]]\s*$", "", title).strip()

    body_text = ""
    for script in soup.find_all("script"):
        text = script.string or ""
        match = re.search(r"var\s+shareDes\s*=\s*`([\s\S]*?)`\s*;", text)
        if match:
            body_text = re.sub(r"<[^>]*>", "", match.group(1))
            body_text = re.sub(r"\s+\n", "\n", body_text)
            body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()
            break

    source_metadata = SourceMetadata(raw=_extract_metadata_from_script(soup, url))

    interpret_links: list[str] = []

    return ParseDetailResult(
        title=title,
        body_text=body_text,
        source_metadata=source_metadata,
        attachments=[],
        interpret_links=interpret_links,
    )
