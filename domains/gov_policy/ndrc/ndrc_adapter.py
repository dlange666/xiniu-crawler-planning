"""国家发改委 (www.ndrc.gov.cn) 政策文件库适配器。

入口：https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/  (发展改革委令 列表页)

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
    "host": "www.ndrc.gov.cn",
    "schema_version": 2,                 # rev 2: 加翻页 + interpret_links
    "data_kind": "policy",
    "supported_modes": ["full"],
    "render_mode": "direct",          # SSR 站点，httpx 直连足够
    "list_url_pattern": r"^https?://www\.ndrc\.gov\.cn/xxgk/zcfb/.*",
    "detail_url_pattern": (
        r"^https?://www\.ndrc\.gov\.cn/xxgk/(?:zcfb|jd)/.*?"
        r"\d{6}/t\d{8}_\d+\.html$"
    ),
    "last_verified_at": "2026-04-28",
    "owner_context": "gov_policy",
}

# 详情页文件名模式：t<YYYYMMDD>_<id>.html
_DETAIL_LINK_RE = re.compile(r"t\d{8}_\d+\.html$")
# 解读 / 图解路径
_INTERPRET_RE = re.compile(r"/xxgk/jd/(?:jd|zctj)/", re.IGNORECASE)
# 主政策路径（扇出列表页中的详情链接需匹配）
_MAIN_POLICY_RE = re.compile(r"/xxgk/zcfb/", re.IGNORECASE)


def build_list_url(seed: SeedSpec, page: int) -> str:
    """构造列表页 URL。仅 page=0 强约束；翻页由 parse_list 自己暴露给引擎。"""
    if not seed.entry_urls:
        msg = "seed.entry_urls is empty"
        raise ValueError(msg)
    if page == 0:
        return seed.entry_urls[0]
    msg = f"ndrc adapter: pagination is parsed dynamically, not by build_list_url(page={page})"
    raise NotImplementedError(msg)


def parse_list(html: str, url: str) -> ParseListResult:
    """解析列表页：提详情链接 + 探翻页。"""
    soup = BeautifulSoup(html, "lxml")

    # 详情链接（仅主政策；解读链接由 parse_detail 阶段从主政策页内发现）
    detail_links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = a["href"]
        if not _DETAIL_LINK_RE.search(href):
            continue
        absolute = urljoin(url, href)
        if not _MAIN_POLICY_RE.search(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        detail_links.append(absolute)

    # 翻页：调通用 helper
    next_pages: list[str] = []
    cph = parse_create_page_html(html)
    if cph is not None:
        total, prefix, suffix = cph
        next_pages = expand_create_page_html_pages(url, total, prefix, suffix)

    return ParseListResult(
        detail_links=detail_links,
        next_pages=next_pages,
        next_page=None,
        stop=False,
    )


# ─── 详情页解析 ─────────────────────────────────────

_META_LABEL_KEYS = (
    "发布时间", "来源", "索引号", "发文字号", "主题分类", "成文日期",
    "公文种类", "发文机关", "发布机关",
)
# 改进的元数据正则：value 取至下一个 label 或换行；非贪婪
_META_VALUE_RE_TPL = (
    r"{label}\s*[:：]\s*"
    r"([^\s\n　]+(?:\s[^\s\n　]+){{0,5}}?)"   # 最多 6 个 token
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
        soup.find("div", class_="pages_content"),
        soup.find("div", id="UCAP-CONTENT"),
    ]
    for c in candidates:
        if isinstance(c, Tag):
            return c
    return None


def parse_detail(html: str, url: str) -> ParseDetailResult:
    soup = BeautifulSoup(html, "lxml")

    # 标题
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            raw = t.get_text(strip=True)
            title = re.sub(r"-国家发展和改革委员会\s*$", "", raw)
            title = re.sub(r"^[【\[]\s*|\s*[】\]]\s*$", "", title).strip()

    # 正文
    container = _find_article_container(soup)
    if container is not None:
        body_text = container.get_text("\n", strip=True)
    else:
        body_text = soup.get_text("\n", strip=True)

    # 元数据
    meta_dict = _extract_metadata_from_text(body_text[:2000])
    metadata = SourceMetadata(raw=meta_dict)

    # 附件 + 外链 + 解读链接
    attachments: list[Attachment] = []
    raw_links: list[str] = []
    interpret_links: list[str] = []
    interpret_seen: set[str] = set()
    if container is not None:
        for a in container.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href = a["href"]
            absolute = urljoin(url, href)
            raw_links.append(absolute)
            lower = absolute.lower()
            if any(lower.endswith(ext) for ext in
                   (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ofd")):
                fname = absolute.rsplit("/", 1)[-1]
                attachments.append(Attachment(url=absolute, filename=fname))
            elif _INTERPRET_RE.search(absolute) and absolute not in interpret_seen:
                interpret_seen.add(absolute)
                interpret_links.append(absolute)

    return ParseDetailResult(
        title=title or "(no title)",
        body_text=body_text,
        source_metadata=metadata,
        attachments=attachments,
        raw_links=raw_links,
        interpret_links=interpret_links,
    )
