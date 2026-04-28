"""gov_policy 业务域领域实体。

spec: docs/prod-spec/domain-gov-policy.md §8 子模块布局
+ docs/prod-spec/codegen-output-contract.md §2.3 数据返回类型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskSpec:
    """采集任务规格（来自外部 task 项目）。MVP 简化版。"""

    task_id: int
    business_context: str = "gov_policy"
    site_url: str = ""
    data_kind: str = "policy"
    max_pages_per_run: int | None = None
    politeness_rps: float = 0.5
    crawl_mode: str = "full"  # full | incremental


@dataclass
class SeedSpec:
    """单 host seed 配置（domains/gov_policy/seeds/<host>.yaml 加载后）。"""

    host: str
    entry_urls: list[str]
    politeness_rps: float = 0.5
    max_pages_per_run: int | None = None
    crawl_mode: str = "full"


@dataclass
class Attachment:
    """详情页发现的附件（PDF / DOC / IMG ...）；MVP 仅记录 URL，不下载内容。"""

    url: str
    filename: str | None = None
    mime: str | None = None


@dataclass
class SourceMetadata:
    """详情页右侧/上方的元信息表（标题、发文字号、发布机关、发布日期等）。

    保留 source 原始 key-value，不做语义归一（语义归一由 AI 抽取阶段做）。
    """

    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseListResult:
    """adapter.parse_list 输出。"""

    detail_links: list[str] = field(default_factory=list)
    next_page: str | None = None
    stop: bool = False  # adapter 判定可停（如已到 crawl_until 日期前）


@dataclass
class ParseDetailResult:
    """adapter.parse_detail 输出。"""

    title: str
    body_text: str
    source_metadata: SourceMetadata = field(default_factory=SourceMetadata)
    attachments: list[Attachment] = field(default_factory=list)
    raw_links: list[str] = field(default_factory=list)


@dataclass
class PolicyParsed:
    """通用 parse/orchestrator 综合输出，准备入 sink。"""

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
