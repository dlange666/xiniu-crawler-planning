"""国家金融监督管理总局 (www.nfra.gov.cn) 政策文件库适配器。

入口：https://www.nfra.gov.cn/cn/view/pages/zhengwuxinxi/zhengfuxinxi.html
API: /cbircweb/solr/openGovSerch (列表), /cbircweb/DocInfo/SelectByDocId (详情)

spec: docs/prod-spec/codegen-output-contract.md §2 (ADAPTER_META + hook 协议)
"""

from __future__ import annotations

import contextlib
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from infra.crawl.types import (
    Attachment,
    ParseDetailResult,
    ParseListResult,
    SeedSpec,
    SourceMetadata,
)

ADAPTER_META: dict = {
    "host": "www.nfra.gov.cn",
    "schema_version": 1,
    "data_kind": "policy",
    "supported_modes": ["full"],
    "render_mode": "direct",
    "list_url_pattern": r"^https?://www\.nfra\.gov\.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild/",
    "detail_url_pattern": r"^https?://www\.nfra\.gov\.cn/cbircweb/DocInfo/SelectByDocId\?.*docId=",
    "last_verified_at": "2026-04-29",
    "owner_context": "gov_policy",
}

_LIST_API_URL = "https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild/data_itemId=861,pageIndex={page},pageSize=18.json"
_DETAIL_API_BASE = "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectByDocId"


def build_list_url(seed: SeedSpec, page: int) -> str:
    """构造列表页静态 JSON 缓存 URL。

    NFRA 使用静态 JSON 缓存：https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild/...
    page 参数映射：page 0/1 -> pageIndex=1，page N -> pageIndex=N+1
    """
    return _LIST_API_URL.format(page=page + 1)


def parse_list(html: str, url: str) -> ParseListResult:
    """解析列表页 JSON：提取详情链接 + 探翻页。

    支持两种格式：
    - POST API: data.lists[]
    - 静态 JSON 缓存: data.rows[]
    """
    data = json.loads(html)

    if data.get("rptCode") != 200:
        return ParseListResult(detail_links=[], next_pages=[], next_page=None, stop=True)

    result_data = data.get("data", {})

    # 支持两种格式：POST API (lists) 和静态 JSON 缓存 (rows)
    items = result_data.get("lists", []) or result_data.get("rows", [])
    total = result_data.get("total", 0)

    detail_links: list[str] = []
    for item in items:
        doc_id = item.get("docId")
        if doc_id:
            detail_url = f"{_DETAIL_API_BASE}?docId={doc_id}"
            detail_links.append(detail_url)

    # 翻页逻辑：从 URL 提取 pageIndex
    next_pages: list[str] = []
    parsed = urlparse(url)
    path = parsed.path
    match = re.search(r"pageIndex=(\d+)", path)
    current_page = 1
    if match:
        with contextlib.suppress(ValueError):
            current_page = int(match.group(1))

    page_size = len(items)
    if page_size > 0 and current_page * page_size < total:
        next_pages.append(build_list_url_from_page(current_page + 1))

    return ParseListResult(
        detail_links=detail_links,
        next_pages=next_pages,
        next_page=None,
        stop=False,
    )


def build_list_url_from_page(page: int) -> str:
    """Helper for building page URL."""
    return _LIST_API_URL.format(page=page)


def _parse_attachment_info(attachment_info: list | None) -> list[Attachment]:
    """解析附件列表。"""
    if not attachment_info:
        return []
    attachments: list[Attachment] = []
    for att in attachment_info:
        file_name = att.get("fileName", "")
        file_url = att.get("fileUrl", "")
        if file_url:
            attachments.append(Attachment(url=file_url, filename=file_name))
    return attachments


def _parse_interpret_links(remark2: str | None) -> list[str]:
    """解析 remark2 字段中的解读链接。"""
    if not remark2:
        return []
    links: list[str] = []
    pattern = r"https?://[^\s\)）]+"
    matches = re.findall(pattern, remark2)
    for match in matches:
        if "nfra.gov.cn" in match:
            links.append(match.rstrip(")）"))
    return links


def parse_detail(html: str, url: str) -> ParseDetailResult:
    """解析详情页 JSON：提取标题、正文、元数据、附件、解读链接。"""
    data = json.loads(html)

    if data.get("rptCode") != 200:
        return ParseDetailResult(
            title="(API error)",
            body_text="",
            source_metadata=SourceMetadata(raw={}),
            attachments=[],
            raw_links=[],
            interpret_links=[],
        )

    result_data = data.get("data", {})

    title = result_data.get("docTitle", "")
    doc_subtitle = result_data.get("docSubtitle", "")
    if doc_subtitle and not title:
        title = doc_subtitle

    body_html = result_data.get("docClob", "")
    body_text = ""
    if body_html:
        soup = BeautifulSoup(body_html, "lxml")
        body_text = soup.get_text("\n", strip=True)

    metadata_raw = {
        "publishDate": result_data.get("publishDate", ""),
        "indexNo": result_data.get("indexNo", ""),
        "documentNo": result_data.get("documentNo", ""),
        "docSource": result_data.get("docSource", ""),
    }
    metadata = SourceMetadata(raw={k: v for k, v in metadata_raw.items() if v})

    attachment_info = result_data.get("attachmentInfoVOList")
    attachments = _parse_attachment_info(attachment_info)

    remark2 = result_data.get("remark2")
    interpret_links = _parse_interpret_links(remark2)

    raw_links: list[str] = []
    if body_html:
        soup = BeautifulSoup(body_html, "lxml")
        for a in soup.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href = a["href"]
            if href.startswith("http"):
                raw_links.append(href)

    return ParseDetailResult(
        title=title or "(no title)",
        body_text=body_text,
        source_metadata=metadata,
        attachments=attachments,
        raw_links=raw_links,
        interpret_links=interpret_links,
    )
