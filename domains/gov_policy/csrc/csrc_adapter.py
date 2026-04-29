"""中国证券监督管理委员会 (www.csrc.gov.cn) 政策文件库适配器。

入口：http://www.csrc.gov.cn/csrc/c106256/fg.shtml (规章列表页)

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
    Attachment,
    ParseDetailResult,
    ParseListResult,
    SeedSpec,
    SourceMetadata,
)

ADAPTER_META: dict = {
    "host": "www.csrc.gov.cn",
    "schema_version": 1,
    "data_kind": "policy",
    "supported_modes": ["full"],
    "render_mode": "direct",
    "list_url_pattern": r"^https?://www\.csrc\.gov\.cn/csrc/c\d+/.*?fg\.shtml$",
    "detail_url_pattern": r"^https?://www\.csrc\.gov\.cn/csrc/c\d+/.*?content\.shtml$",
    "last_verified_at": "2026-04-29",
    "owner_context": "gov_policy",
}

_DETAIL_LINK_RE = re.compile(r"/csrc/c\d+/content\.shtml$")
_CSRC_CREATE_PAGE_RE = re.compile(
    r"createPageHTML\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(\d+)\s*,\s*\d+\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]"
)


def _parse_csrc_create_page_html(html: str) -> tuple[int, str, str] | None:
    """Parse CSRC's createPageHTML('page_div', total, cur, prefix, suffix, rows)."""
    match = _CSRC_CREATE_PAGE_RE.search(html)
    if not match:
        return None
    return int(match.group(1)), match.group(2), match.group(3)


def build_list_url(seed: SeedSpec, page: int) -> str:
    """构造列表页 URL。仅 page=0 强约束；翻页由 parse_list 自己暴露给引擎。"""
    if not seed.entry_urls:
        msg = "seed.entry_urls is empty"
        raise ValueError(msg)
    if page == 0:
        return seed.entry_urls[0]
    msg = "csrc adapter: pagination is parsed dynamically, not by build_list_url(page={page})"
    raise NotImplementedError(msg)


def parse_list(html: str, url: str) -> ParseListResult:
    """解析列表页：提取详情链接 + 探翻页。"""
    soup = BeautifulSoup(html, "lxml")

    detail_links: list[str] = []
    seen: set[str] = set()
    tbody = soup.find("tbody", id="zc-list-content")
    if tbody:
        for a in tbody.find_all("a", class_="list", href=True):
            href = a["href"]
            if not href or href == "#":
                continue
            absolute = urljoin(url, href)
            if absolute in seen:
                continue
            seen.add(absolute)
            detail_links.append(absolute)

    next_pages: list[str] = []
    cph = parse_create_page_html(html)
    if cph is None:
        cph = _parse_csrc_create_page_html(html)
    if cph is not None:
        total, prefix, suffix = cph
        next_pages = expand_create_page_html_pages(url, total, prefix, suffix)

    return ParseListResult(
        detail_links=detail_links,
        next_pages=next_pages,
        next_page=None,
        stop=False,
    )


_META_LABEL_KEYS = (
    "发布机构",
    "发文字号",
    "主题分类",
    "成文日期",
    "发布日期",
    "公开方式",
)
_META_VALUE_RE_TPL = (
    r"{label}\s*[:：]\s*"
    r"([^\s\n　]+(?:\s[^\s\n　]+){{0,5}})"
    r"(?=\s*(?:{stop_labels}|\n|$))"
)


def _extract_metadata_from_text(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    other_labels = "|".join(re.escape(k) + r"\s*[:：]" for k in _META_LABEL_KEYS)
    for label in _META_LABEL_KEYS:
        pat = _META_VALUE_RE_TPL.format(label=label, stop_labels=other_labels)
        m = re.search(pat, text)
        if m:
            meta[label] = m.group(1).strip()
    return meta


def _find_article_container(soup: BeautifulSoup) -> Tag | None:
    candidates = [
        soup.find("div", class_="article"),
        soup.find("div", class_="TRS_Editor"),
        soup.find("div", class_="content"),
        soup.find("div", id="UCAP-CONTENT"),
    ]
    for c in candidates:
        if isinstance(c, Tag):
            return c
    return None


def _extract_meta_tags(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for meta_tag in soup.find_all("meta"):
        name = meta_tag.get("name") or meta_tag.get("property")
        content = meta_tag.get("content")
        if name and content and name in (
            "ArticleTitle",
            "PubDate",
            "ContentSource",
            "Keywords",
            "Description",
        ):
            if name == "ArticleTitle":
                meta["标题"] = content
            elif name == "PubDate":
                meta["发布日期"] = content
            elif name == "ContentSource":
                meta["发布机构"] = content
            elif name == "Keywords":
                meta["关键词"] = content
            elif name == "Description":
                meta["摘要"] = content
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
            title = re.sub(r"-中国证券监督管理委员会\s*$", "", raw)
            title = re.sub(r"^[【\[]\s*|\s*[】\]]\s*$", "", title).strip()

    meta_dict = _extract_meta_tags(soup)

    container = _find_article_container(soup)
    if container is not None:
        body_text = container.get_text("\n", strip=True)
        sub_title = container.find("p", class_="sub-title")
        if sub_title:
            sub_text = sub_title.get_text(strip=True)
            if "令第" in sub_text:
                match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日).*?(令第\d+号)", sub_text)
                if match:
                    meta_dict["发布日期"] = match.group(1)
                    meta_dict["发文字号"] = match.group(2)
    else:
        body_text = soup.get_text("\n", strip=True)

    text_meta = _extract_metadata_from_text(body_text[:2000])
    meta_dict.update(text_meta)

    metadata = SourceMetadata(raw=meta_dict)

    attachments: list[Attachment] = []
    raw_links: list[str] = []
    if container is not None:
        for a in container.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href = a["href"]
            absolute = urljoin(url, href)
            raw_links.append(absolute)
            if any(
                absolute.lower().endswith(ext)
                for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ofd")
            ):
                fname = absolute.rsplit("/", 1)[-1]
                attachments.append(Attachment(url=absolute, filename=fname))

    return ParseDetailResult(
        title=title or "(no title)",
        body_text=body_text,
        source_metadata=metadata,
        attachments=attachments,
        raw_links=raw_links,
        interpret_links=[],
    )
