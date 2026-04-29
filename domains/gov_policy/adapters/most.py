"""科学技术部 (www.most.gov.cn) 政策文件库适配器。

入口：https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/ （法规政策）

spec: docs/prod-spec/codegen-output-contract.md §2 (ADAPTER_META + hook 协议)
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from infra.crawl.types import (
    Attachment,
    ParseDetailResult,
    ParseListResult,
    SeedSpec,
    SourceMetadata,
)

ADAPTER_META: dict = {
    "host": "www.most.gov.cn",
    "schema_version": 2,
    "data_kind": "policy",
    "supported_modes": ["full"],
    "render_mode": "direct",
    "list_url_pattern": r"^https?://www\.most\.gov\.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/.*",
    "detail_url_pattern": (
        r"^https?://www\.most\.gov\.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/"
        r"(?:flfg|bmgz|gfxwj)/.*?/t\d{8}_\d+\.html$"
    ),
    "last_verified_at": "2026-04-28",
    "owner_context": "gov_policy",
}

_DETAIL_LINK_RE = re.compile(r"t\d{8}_\d+\.html$")
_MAIN_POLICY_RE = re.compile(r"/fgzc/(?:flfg|bmgz|gfxwj)/", re.IGNORECASE)
_INTERPRET_RE = re.compile(r"/fgzc/zcjd/", re.IGNORECASE)
_ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ofd")


def build_list_url(seed: SeedSpec, page: int) -> str:
    if not seed.entry_urls:
        msg = "seed.entry_urls is empty"
        raise ValueError(msg)
    if page == 0:
        return seed.entry_urls[0]
    msg = f"most adapter: pagination not implemented via build_list_url(page={page})"
    raise NotImplementedError(msg)


def parse_list(html: str, url: str) -> ParseListResult:
    soup = BeautifulSoup(html, "lxml")
    detail_links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = a["href"]
        if not _DETAIL_LINK_RE.search(href):
            continue
        absolute = urljoin(url, href)
        if urlparse(absolute).netloc != "www.most.gov.cn":
            continue
        if not _MAIN_POLICY_RE.search(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        detail_links.append(absolute)

    return ParseListResult(
        detail_links=detail_links,
        next_pages=[],
        next_page=None,
        stop=True,
    )


_META_LABEL_ALIASES = {
    "标题": "标题",
    "索引号": "索引号",
    "发文机构": "发文机构",
    "成文日期": "成文日期",
    "发布日期": "发布日期",
    "发文字号": "发文字号",
    "有效性": "有效性",
}


def _clean_label(text: str) -> str:
    compact = re.sub(r"\s+", "", text.replace("\u3000", ""))
    compact = compact.replace(":", "").replace("：", "")
    return _META_LABEL_ALIASES.get(compact, "")


def _clean_value(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def _extract_metadata_from_table(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    table = soup.find("table", class_="xxgk_detail_table1")
    if not table:
        return meta
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        for idx in range(0, len(cells) - 1, 2):
            label = _clean_label(cells[idx].get_text(" ", strip=True))
            value = _clean_value(cells[idx + 1].get_text(" ", strip=True))
            if label and value:
                meta[label] = value
    return meta


def _find_article_container(soup: BeautifulSoup) -> Tag | None:
    zoom = soup.find("div", id="Zoom")
    if zoom:
        return zoom
    content = soup.find("div", class_="xxgk_detail_content")
    if content:
        return content
    return None


def _iter_links(soup: BeautifulSoup, url: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    content = soup.find("div", class_="xxgk_detail_content") or soup
    for a in content.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = str(a["href"]).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        absolute = urljoin(url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append((_clean_value(a.get_text(" ", strip=True)), absolute))
    return links


def parse_detail(html: str, url: str) -> ParseDetailResult:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        meta_title = soup.find("meta", attrs={"name": "ArticleTitle"})
        if meta_title and meta_title.get("content"):
            title = meta_title["content"]
    if not title:
        title_div = soup.find("div", class_="xxgk_title")
        if title_div:
            title = title_div.get_text(strip=True)

    container = _find_article_container(soup)
    if container is not None:
        body_text = _clean_value(container.get_text("\n", strip=True))
    else:
        body_text = _clean_value(soup.get_text("\n", strip=True))

    meta_dict = _extract_metadata_from_table(soup)
    metadata = SourceMetadata(raw=meta_dict)

    attachments: list[Attachment] = []
    raw_links: list[str] = []
    interpret_links: list[str] = []
    for text, absolute in _iter_links(soup, url):
        raw_links.append(absolute)
        lower = absolute.lower()
        if any(lower.endswith(ext) for ext in _ATTACHMENT_EXTENSIONS):
            fname = text or absolute.rsplit("/", 1)[-1]
            attachments.append(Attachment(url=absolute, filename=fname))
        elif _INTERPRET_RE.search(absolute):
            interpret_links.append(absolute)

    return ParseDetailResult(
        title=title or "(no title)",
        body_text=body_text,
        source_metadata=metadata,
        attachments=attachments,
        raw_links=raw_links,
        interpret_links=interpret_links,
    )
