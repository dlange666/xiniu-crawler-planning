"""国家发改委 (www.ndrc.gov.cn) 政策文件库适配器。

入口示例：https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/  (发展改革委令 列表页)

spec: docs/prod-spec/codegen-output-contract.md §2 (ADAPTER_META + hook 协议)
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from domains.gov_policy.model import (
    Attachment,
    ParseDetailResult,
    ParseListResult,
    SeedSpec,
    SourceMetadata,
)

ADAPTER_META: dict = {
    "host": "www.ndrc.gov.cn",
    "schema_version": 1,
    "data_kind": "policy",
    "supported_modes": ["full"],
    "list_url_pattern": r"^https?://www\.ndrc\.gov\.cn/xxgk/zcfb/.*",
    "detail_url_pattern": (
        r"^https?://www\.ndrc\.gov\.cn/xxgk/(?:zcfb|jd)/.*?"
        r"\d{6}/t\d{8}_\d+\.html$"
    ),
    "last_verified_at": "2026-04-28",
    "owner_context": "gov_policy",
}

_DETAIL_LINK_RE = re.compile(r"t\d{8}_\d+\.html$")


def build_list_url(seed: SeedSpec, page: int) -> str:
    """构造列表页 URL。MVP 仅支持 page=0（首页）；翻页延后。"""
    if not seed.entry_urls:
        msg = "seed.entry_urls is empty"
        raise ValueError(msg)
    if page == 0:
        return seed.entry_urls[0]
    # 国家发改委分页是 JS 注入的，MVP 暂不实现翻页
    msg = f"ndrc adapter MVP only supports page=0, got page={page}"
    raise NotImplementedError(msg)


def parse_list(html: str, url: str) -> ParseListResult:
    """从列表页提取详情页 URL。"""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    # 粗筛：所有 a[href] 中匹配 t<YYYYMMDD>_<id>.html 的，且不在导航/侧栏区
    # NDRC 主体文章列表都是 main 区域内的 a
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = a["href"]
        if not _DETAIL_LINK_RE.search(href):
            continue
        absolute = urljoin(url, href)
        # 仅保留主政策（zcfb/fzggwl/...），跳过解读（jd/jd/...）—MVP 简化
        if "/xxgk/zcfb/" not in absolute:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return ParseListResult(detail_links=links, next_page=None, stop=False)


# 元数据提取关键词（NDRC 详情页元信息常见 label）
_META_LABEL_KEYS = (
    "发布时间", "来源", "索引号", "发文字号", "主题分类", "成文日期",
    "公文种类", "发文机关", "发布机关",
)


def _extract_metadata_from_text(text: str) -> dict[str, str]:
    """从纯文本中提取元数据（发布时间/来源/...）。"""
    meta: dict[str, str] = {}
    # 匹配 "label：value" 或 "label: value"
    for label in _META_LABEL_KEYS:
        # 例：'发布时间：2026/04/09'
        m = re.search(rf"{label}\s*[:：]\s*([^\s　]+(?:\s[^\s　]+)?)", text)
        if m:
            meta[label] = m.group(1).strip()
    return meta


def _find_article_container(soup: BeautifulSoup) -> Tag | None:
    """找 NDRC 详情页的正文容器。"""
    # 常见 class："article", "TRS_Editor", "pages_content", "content"
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
    """从详情页提取标题、正文、元数据、附件、外链。"""
    soup = BeautifulSoup(html, "lxml")

    # ─── 标题 ───────────────────────────────────────────
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            # NDRC <title> 形如：【...政策标题...】-国家发展和改革委员会
            raw = t.get_text(strip=True)
            title = re.sub(r"-国家发展和改革委员会\s*$", "", raw)
            title = re.sub(r"^[【\[]\s*|\s*[】\]]\s*$", "", title).strip()

    # ─── 正文 ───────────────────────────────────────────
    container = _find_article_container(soup)
    if container is not None:
        body_text = container.get_text("\n", strip=True)
    else:
        # 兜底：取整文本
        body_text = soup.get_text("\n", strip=True)

    # ─── 元数据（先在 container 里找，再从 body_text 提取）
    meta_dict = _extract_metadata_from_text(body_text[:2000])
    metadata = SourceMetadata(raw=meta_dict)

    # ─── 附件（PDF/DOC/IMG）─────────────────────────────
    attachments: list[Attachment] = []
    raw_links: list[str] = []
    if container is not None:
        for a in container.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href = a["href"]
            absolute = urljoin(url, href)
            raw_links.append(absolute)
            lower = absolute.lower()
            if any(lower.endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx")):
                fname = absolute.rsplit("/", 1)[-1]
                attachments.append(Attachment(url=absolute, filename=fname))

    return ParseDetailResult(
        title=title or "(no title)",
        body_text=body_text,
        source_metadata=metadata,
        attachments=attachments,
        raw_links=raw_links,
    )
