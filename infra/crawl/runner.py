"""通用 CrawlEngine（business-agnostic）。

spec: codegen-output-contract.md §2 + research §3-§4 routing order

设计要点：
1. 通过 adapter_resolver 注入站点适配器（不直接依赖 domains/）
2. BFS/DFS 由 task.strategy + task.max_depth 控制
3. scope 闸口由 task.scope_mode + scope_url_pattern + scope_allowlist_hosts 控制
4. 列表页 next_pages、详情页 interpret_links + attachments 都通过 adapter hook 暴露
   引擎按 BFS 优先级递归入队
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from infra.frontier import Frontier, FrontierItem
from infra.http import HostTokenBucket, HttpClient, HttpResponse
from infra.robots import RobotsChecker
from infra.storage import get_blob_store, get_metadata_store

from .scope import scope_allows
from .strategies import compute_priority
from .types import SeedSpec, TaskSpec

logger = logging.getLogger(__name__)


# adapter 协议：模块需含 ADAPTER_META + parse_list + parse_detail
AdapterResolver = Callable[[str], object]


@dataclass
class RunReport:
    task_id: int
    seed_host: str
    list_pages_fetched: int = 0
    detail_urls_discovered: int = 0
    detail_urls_fetched: int = 0
    interpret_pages_fetched: int = 0
    attachments_fetched: int = 0
    raw_records_written: int = 0
    raw_records_dedup_hit: int = 0
    rejected_by_scope: int = 0
    rejected_by_robots: int = 0
    errors: int = 0
    anti_bot_events: int = 0
    resumed: bool = False
    urls_resumed: int = 0
    failures: list[str] = field(default_factory=list)


def _url_fp(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _content_sha256(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _blob_key(task_id: int, url_hash: str, ts: datetime | None = None,
              ext: str = "html") -> str:
    ts = ts or datetime.now(UTC)
    return (
        f"{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/"
        f"task-{task_id}/{url_hash}.{ext}"
    )


# ─── URL 类型标记（在 frontier item 的 discovery_source 中编码）────────────
DISCOVERY_LIST_PAGE = "list_page"            # depth=0：seed 列表页（首页或翻页）
DISCOVERY_DETAIL = "list_to_detail"          # depth=1：列表页 → 详情链接
DISCOVERY_INTERPRET = "detail_to_interpret"  # depth≥2：详情页 → 解读链接
DISCOVERY_ATTACHMENT = "detail_to_attachment"  # depth≥2：详情页 → 附件


def _is_list_url(discovery_source: str) -> bool:
    return discovery_source == DISCOVERY_LIST_PAGE


def _is_attachment_url(discovery_source: str) -> bool:
    return discovery_source == DISCOVERY_ATTACHMENT


# discovery_source → base_score：与 _submit_if_in_scope 调用点保持一致
# 列表页 0.7 / 详情 0.5 / 解读 0.4 / 附件 0.3
_BASE_SCORE_BY_SOURCE = {
    DISCOVERY_LIST_PAGE: 0.7,
    DISCOVERY_DETAIL: 0.5,
    DISCOVERY_INTERPRET: 0.4,
    DISCOVERY_ATTACHMENT: 0.3,
}


class CrawlEngine:
    def __init__(
        self,
        *,
        task: TaskSpec,
        seed: SeedSpec,
        adapter_resolver: AdapterResolver | None = None,
        run_id: str | None = None,
    ) -> None:
        self.task = task
        self.seed = seed
        # 默认走全局注册表；测试 / 特殊路径可注入自定义 resolver
        if adapter_resolver is None:
            from infra import adapter_registry
            if not adapter_registry.list_all():
                adapter_registry.discover()
            entry = adapter_registry.get(task.business_context, seed.host)
            if entry.render_mode != "direct":
                msg = (
                    f"adapter {entry.module_path} declares "
                    f"render_mode={entry.render_mode!r}; only 'direct' is "
                    "implemented (headless renderer not built yet, see "
                    "architecture.md §5)"
                )
                raise NotImplementedError(msg)
            self.adapter_resolver = (
                lambda host: adapter_registry.get(task.business_context, host).module
            )
        else:
            self.adapter_resolver = adapter_resolver
        self.run_id = run_id or datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")

        # token bucket
        bucket = HostTokenBucket(default_rps=1.0, default_burst=2)
        bucket.configure(
            seed.host, rps=min(seed.politeness_rps, 1.0), burst=1)
        self.http = HttpClient(token_bucket=bucket)

        # robots
        def robots_get(url: str) -> tuple[int, bytes]:
            host = urlparse(url).netloc
            r = self.http.fetch(url, host=host, skip_anti_bot=True)
            return r.status_code, r.body

        self.robots = RobotsChecker(robots_get)

        # frontier 总额度：取 seed 与 task 中的最严
        budget = task.max_pages_per_run or seed.max_pages_per_run
        self.frontier = Frontier(max_pages=budget)

        # storage
        self.metadata = get_metadata_store()
        self.blobs = get_blob_store()
        self.metadata.init_schema()

    def close(self) -> None:
        self.http.close()
        self.metadata.close()

    # ─── 入口 ──────────────────────────────────────────

    def run(self) -> RunReport:
        report = RunReport(task_id=self.task.task_id, seed_host=self.seed.host)
        adapter = self.adapter_resolver(self.seed.host)

        # 0. 续抓检测：已有 url_record 视为续跑，从 pending 队列恢复
        if self.metadata.has_url_records_for_task(task_id=self.task.task_id):
            report.resumed = True
            for row in self.metadata.list_pending_url_records(
                    task_id=self.task.task_id):
                # 已成功落库的 URL 直接标记 done，不再入队
                if self._already_crawled(row["url"]):
                    self.metadata.mark_url_record_state(
                        task_id=self.task.task_id, url_fp=row["url_fp"],
                        state="done")
                    continue
                base_score = _BASE_SCORE_BY_SOURCE.get(
                    row["discovery_source"], 0.5)
                priority = compute_priority(
                    depth=row["depth"],
                    max_depth=max(self.task.max_depth, 1),
                    base_score=base_score, strategy=self.task.strategy,
                )
                self.frontier.submit(FrontierItem(
                    url=row["url"], url_fp=row["url_fp"], host=row["host"],
                    depth=row["depth"], parent_url_fp=row["parent_url_fp"],
                    discovery_source=row["discovery_source"],
                    priority_score=priority,
                ))
                report.urls_resumed += 1
            logger.info(
                "resume task_id=%s resumed=%d pending URLs",
                self.task.task_id, report.urls_resumed)
        else:
            # 1. seed 入队（depth=0，list 类型）
            for entry_url in self.seed.entry_urls:
                allowed, reason = self.robots.is_allowed(entry_url)
                if not allowed:
                    report.rejected_by_robots += 1
                    report.failures.append(
                        f"robots denied seed {entry_url}: {reason}")
                    report.errors += 1
                    return report

                self._submit_url(
                    entry_url, depth=0, parent_url_fp=None,
                    discovery_source=DISCOVERY_LIST_PAGE,
                    base_score=0.7,
                )

        # 2. 主循环
        while True:
            item = self.frontier.next_ready()
            if item is None:
                break
            allowed, _ = self.robots.is_allowed(item.url)
            if not allowed:
                report.rejected_by_robots += 1
                self._mark_done(item)
                continue
            self._process_item(item, adapter, report)

        return report

    # ─── 单条 item 派发 ──────────────────────────────

    def _process_item(self, item: FrontierItem, adapter, report: RunReport) -> None:
        if _is_attachment_url(item.discovery_source):
            self._fetch_attachment(item, report)
        elif _is_list_url(item.discovery_source):
            self._fetch_list(item, adapter, report)
        else:
            # detail / interpret 走同样路径（都是文章页，都要 parse_detail + sink）
            self._fetch_and_sink_detail(item, adapter, report)

    # ─── 列表页 ───────────────────────────────────────

    def _fetch_list(self, item: FrontierItem, adapter, report: RunReport) -> None:
        resp = self.http.fetch(item.url, host=item.host)
        report.list_pages_fetched += 1
        self._record_fetch(item, resp)
        if resp.error_kind:
            report.errors += 1
            if resp.anti_bot_signal:
                report.anti_bot_events += 1
            report.failures.append(
                f"list fetch failed [{resp.error_kind}] {item.url}")
            self._mark_failed(item)
            return

        try:
            list_result = adapter.parse_list(
                resp.body.decode("utf-8", errors="replace"),
                resp.final_url,
            )
        except Exception as e:  # noqa: BLE001
            report.errors += 1
            report.failures.append(f"parse_list failed {item.url}: {e}")
            self._mark_failed(item)
            return

        # 翻页（仍是 depth=0）
        if self.task.scope_follow_pagination:
            for next_url in list_result.next_pages:
                self._submit_if_in_scope(
                    next_url, parent_url=item.url, depth=0,
                    parent_url_fp=item.url_fp,
                    discovery_source=DISCOVERY_LIST_PAGE,
                    base_score=0.7, report=report,
                )

        # 详情链接（depth+1）
        for detail_url in list_result.detail_links:
            self._submit_if_in_scope(
                detail_url, parent_url=item.url, depth=item.depth + 1,
                parent_url_fp=item.url_fp,
                discovery_source=DISCOVERY_DETAIL,
                base_score=0.5, report=report,
            )
            report.detail_urls_discovered += 1

        self._mark_done(item)

    # ─── 详情页 / 解读页 ─────────────────────────────

    def _fetch_and_sink_detail(self, item: FrontierItem, adapter, report: RunReport) -> None:
        # 预查：若已成功抓过（crawl_raw 中已有），跳过 HTTP 请求
        if self._already_crawled(item.url):
            report.raw_records_dedup_hit += 1
            self._mark_done(item)
            return

        resp = self.http.fetch(item.url, host=item.host)
        if item.discovery_source == DISCOVERY_INTERPRET:
            report.interpret_pages_fetched += 1
        else:
            report.detail_urls_fetched += 1
        self._record_fetch(item, resp)

        if resp.error_kind:
            report.errors += 1
            if resp.anti_bot_signal:
                report.anti_bot_events += 1
            report.failures.append(
                f"detail fetch failed [{resp.error_kind}] {item.url}")
            self._mark_failed(item)
            return

        try:
            detail = adapter.parse_detail(
                resp.body.decode("utf-8", errors="replace"),
                resp.final_url,
            )
        except Exception as e:  # noqa: BLE001
            report.errors += 1
            report.failures.append(f"parse_detail failed {item.url}: {e}")
            self._mark_failed(item)
            return

        url_hash = hashlib.sha256(item.url.encode("utf-8")).hexdigest()
        body_sha = _content_sha256(detail.body_text)

        key = _blob_key(self.task.task_id, url_hash[:16])
        blob_uri = self.blobs.put(
            key, resp.body,
            content_type=resp.headers.get("content-type"),
        )

        data_payload = {
            "title": detail.title,
            "body_text": detail.body_text[:50000],
            "source_metadata": detail.source_metadata.raw,
            "attachments": [
                {"url": a.url, "filename": a.filename, "mime": a.mime}
                for a in detail.attachments
            ],
            "interpret_links": detail.interpret_links,
            "raw_links": detail.raw_links,
            "raw_links_count": len(detail.raw_links),
            "interpret_links_count": len(detail.interpret_links),
            "discovery_source": item.discovery_source,
        }
        inserted = self.metadata.insert_crawl_raw(
            task_id=self.task.task_id,
            business_context=self.task.business_context,
            host=item.host, url=item.url, canonical_url=resp.final_url,
            url_hash=url_hash, content_sha256=body_sha,
            raw_blob_uri=blob_uri,
            data_json=json.dumps(data_payload, ensure_ascii=False),
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
            run_id=self.run_id,
        )
        if inserted:
            report.raw_records_written += 1
        else:
            report.raw_records_dedup_hit += 1

        # 递归发现下一层（仅当未触 max_depth）
        if item.depth < self.task.max_depth:
            # 解读页（仍按 detail 处理，但 discovery_source 不同）
            for link in detail.interpret_links:
                self._submit_if_in_scope(
                    link, parent_url=item.url, depth=item.depth + 1,
                    parent_url_fp=item.url_fp,
                    discovery_source=DISCOVERY_INTERPRET,
                    base_score=0.4, report=report,
                )
            # 附件（fetch_only，不 parse_detail）
            for att in detail.attachments:
                self._submit_if_in_scope(
                    att.url, parent_url=item.url, depth=item.depth + 1,
                    parent_url_fp=item.url_fp,
                    discovery_source=DISCOVERY_ATTACHMENT,
                    base_score=0.3, report=report,
                )

        self._mark_done(item)

    # ─── 附件下载（仅落 blob，不 parse）─────────────

    def _fetch_attachment(self, item: FrontierItem, report: RunReport) -> None:
        resp = self.http.fetch(item.url, host=item.host)
        report.attachments_fetched += 1
        self._record_fetch(item, resp)

        if resp.error_kind:
            report.errors += 1
            if resp.anti_bot_signal:
                report.anti_bot_events += 1
            report.failures.append(
                f"attachment fetch failed [{resp.error_kind}] {item.url}")
            self._mark_failed(item)
            return

        # 推断扩展名
        url_path = urlparse(item.url).path
        ext = url_path.rsplit(".", 1)[-1].lower() if "." in url_path else "bin"
        url_hash = hashlib.sha256(item.url.encode("utf-8")).hexdigest()
        key = _blob_key(self.task.task_id, url_hash[:16], ext=ext)
        self.blobs.put(
            key, resp.body,
            content_type=resp.headers.get("content-type"),
        )
        # 附件不写 crawl_raw（业务侧 sink 决定要不要建 attachment 表）
        self._mark_done(item)

    # ─── 共用辅助 ────────────────────────────────────

    def _record_fetch(self, item: FrontierItem, resp: HttpResponse) -> None:
        """写 fetch_record；attempt 由 storage 自动递增（重启不冲突）。"""
        self.metadata.insert_fetch_record(
            task_id=self.task.task_id, url_fp=item.url_fp,
            status_code=resp.status_code or None,
            content_type=resp.headers.get("content-type"),
            bytes_received=len(resp.body) if resp.body else None,
            latency_ms=resp.elapsed_ms,
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
            error_kind=resp.error_kind, error_detail=resp.error_detail,
        )

    def _mark_done(self, item: FrontierItem) -> None:
        self.metadata.mark_url_record_state(
            task_id=self.task.task_id, url_fp=item.url_fp, state="done")

    def _mark_failed(self, item: FrontierItem) -> None:
        self.metadata.mark_url_record_state(
            task_id=self.task.task_id, url_fp=item.url_fp, state="failed")

    def _already_crawled(self, url: str) -> bool:
        """该 URL 是否已成功抓取过（crawl_raw 中已有）。

        用于重启续抓：跳过已成功的 URL，避免重发请求。
        """
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.metadata.is_url_in_crawl_raw(url_hash=url_hash)

    def _submit_url(
        self, url: str, *, depth: int, parent_url_fp: str | None,
        discovery_source: str, base_score: float,
    ) -> bool:
        fp = _url_fp(url)
        host = urlparse(url).netloc
        self.metadata.upsert_url_record(
            task_id=self.task.task_id, url_fp=fp, url=url, host=host,
            depth=depth, parent_url_fp=parent_url_fp,
            discovery_source=discovery_source,
        )
        priority = compute_priority(
            depth=depth, max_depth=max(self.task.max_depth, 1),
            base_score=base_score, strategy=self.task.strategy,
        )
        return self.frontier.submit(FrontierItem(
            url=url, url_fp=fp, host=host,
            depth=depth, parent_url_fp=parent_url_fp,
            discovery_source=discovery_source,
            priority_score=priority,
        ))

    def _submit_if_in_scope(
        self, candidate_url: str, *, parent_url: str, depth: int,
        parent_url_fp: str | None, discovery_source: str,
        base_score: float, report: RunReport,
    ) -> bool:
        allowed, _reason = scope_allows(
            candidate_url=candidate_url, parent_url=parent_url,
            mode=self.task.scope_mode,
            url_pattern=self.task.scope_url_pattern,
            allowlist_hosts=self.task.scope_allowlist_hosts,
        )
        if not allowed:
            report.rejected_by_scope += 1
            return False
        return self._submit_url(
            candidate_url, depth=depth, parent_url_fp=parent_url_fp,
            discovery_source=discovery_source, base_score=base_score,
        )
