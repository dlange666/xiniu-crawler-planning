"""引擎契约类型（spec: codegen-output-contract.md §2.3）。

跨业务域共用；具体业务字段定义在各 domain 的 spec 与 adapter 中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


@dataclass
class TaskSpec:
    """任务级配置（来自外部 task 项目）。MVP 简化版。

    完整字段见 docs/prod-spec/data-model.md §4.1.1（外部项目实现）。
    """

    task_id: int
    business_context: str = "gov_policy"

    # ── 调度策略 ─────────────────────
    strategy: Literal["bfs", "dfs"] = "bfs"
    max_depth: int = 1                      # 0=只 seed；1=seed+detail；2=+解读/附件
    max_pages_per_run: int | None = None

    # ── 作用域 ──────────────────────
    scope_mode: Literal[
        "same_origin", "same_etld_plus_one", "url_pattern", "allowlist"
    ] = "same_origin"
    scope_url_pattern: str | None = None
    scope_allowlist_hosts: list[str] = field(default_factory=list)
    scope_follow_canonical: bool = True
    scope_follow_pagination: bool = True

    # ── 限速 ────────────────────────
    politeness_rps: float = 0.5

    # ── 应用层增量 ──────────────────
    crawl_mode: Literal["full", "incremental"] = "full"
    crawl_until: date | None = None
    site_url: str = ""
    data_kind: str = "policy"


@dataclass
class SeedSpec:
    """单 host seed 配置。"""

    host: str
    entry_urls: list[str]
    politeness_rps: float = 0.5
    max_pages_per_run: int | None = None
    crawl_mode: str = "full"


@dataclass
class Attachment:
    url: str
    filename: str | None = None
    mime: str | None = None


@dataclass
class SourceMetadata:
    """详情页右侧/上方的元信息表（标题、发文字号、发布机关...）。"""

    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseListResult:
    """adapter.parse_list 输出。"""

    detail_links: list[str] = field(default_factory=list)
    next_pages: list[str] = field(default_factory=list)   # 翻页 URL（可多个）
    next_page: str | None = None                          # 兼容字段（单"下一页"模式）
    stop: bool = False


@dataclass
class ParseDetailResult:
    """adapter.parse_detail 输出。"""

    title: str
    body_text: str
    source_metadata: SourceMetadata = field(default_factory=SourceMetadata)
    attachments: list[Attachment] = field(default_factory=list)
    raw_links: list[str] = field(default_factory=list)
    interpret_links: list[str] = field(default_factory=list)  # 同政策的解读/图解


@dataclass
class PolicyParsed:
    """通用 parse 综合输出，准备入 sink。"""

    task_id: int
    business_context: str
    host: str
    url: str
    canonical_url: str
    detail: ParseDetailResult
    raw_blob_uri: str
    content_sha256: str
    url_hash: str
    etag: str | None = None
    last_modified: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
