"""采集 runner：seed → list → detail → sink。

一个简单的三步循环：
  1. fetch list 页 → adapter.parse_list → 拿到详情页 URL 列表
  2. 入 frontier
  3. 循环 next_ready → fetch detail → adapter.parse_detail → 计算指纹 → 落库（去重）
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from domains.gov_policy import adapters
from domains.gov_policy.model import SeedSpec, TaskSpec
from infra.frontier import Frontier, FrontierItem
from infra.http import HostTokenBucket, HttpClient, HttpResponse
from infra.robots import RobotsChecker
from infra.storage import get_blob_store, get_metadata_store

logger = logging.getLogger(__name__)


@dataclass
class RunReport:
    task_id: int
    seed_host: str
    list_pages_fetched: int = 0
    detail_urls_discovered: int = 0
    detail_urls_fetched: int = 0
    raw_records_written: int = 0
    raw_records_dedup_hit: int = 0
    errors: int = 0
    anti_bot_events: int = 0
    failures: list[str] = field(default_factory=list)


def _url_fp(url: str) -> str:
    """简化的 URL 指纹：SHA-256(canonical_url) hex 前 32 位。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _content_sha256(text: str) -> str:
    """正文规范化后取 SHA-256。规范化：strip + 内部空白合一。"""
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _blob_key(task_id: int, url_hash: str, ts: datetime | None = None) -> str:
    ts = ts or datetime.now(UTC)
    return (
        f"{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/"
        f"task-{task_id}/{url_hash}.html"
    )


class CrawlRunner:
    def __init__(
        self,
        *,
        task: TaskSpec,
        seed: SeedSpec,
        run_id: str | None = None,
    ) -> None:
        self.task = task
        self.seed = seed
        self.run_id = run_id or datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")

        # token bucket：seed.politeness_rps 仅向下覆盖默认 0.5
        bucket = HostTokenBucket(default_rps=0.5, default_burst=2)
        bucket.configure(seed.host, rps=min(seed.politeness_rps, 0.5), burst=1)
        self.http = HttpClient(token_bucket=bucket)

        # robots 复用同一个 http 客户端，但豁免反爬识别
        # （robots.txt 4xx/5xx 由 RobotsChecker 按 RFC 9309 自行决策，
        #  不应触发 host cooldown）
        def robots_get(url: str) -> tuple[int, bytes]:
            host = urlparse(url).netloc
            r = self.http.fetch(url, host=host, skip_anti_bot=True)
            return r.status_code, r.body

        self.robots = RobotsChecker(robots_get)
        self.frontier = Frontier(max_pages=seed.max_pages_per_run)
        self.metadata = get_metadata_store()
        self.blobs = get_blob_store()
        self.metadata.init_schema()

    def close(self) -> None:
        self.http.close()
        self.metadata.close()

    # ─── 主流程 ───────────────────────────────────────────

    def run(self) -> RunReport:
        report = RunReport(task_id=self.task.task_id, seed_host=self.seed.host)

        # 1. robots 闸口：seed entry URL 必须被允许
        for entry_url in self.seed.entry_urls:
            allowed, reason = self.robots.is_allowed(entry_url)
            if not allowed:
                msg = f"robots denied for {entry_url}: {reason}"
                logger.error(msg)
                report.failures.append(msg)
                report.errors += 1
                return report

        # 2. 抓列表页 → 提详情链接
        adapter = adapters.resolve(self.seed.host)
        for entry_url in self.seed.entry_urls:
            list_resp = self.http.fetch(entry_url, host=self.seed.host)
            report.list_pages_fetched += 1
            if list_resp.error_kind:
                report.errors += 1
                if list_resp.anti_bot_signal:
                    report.anti_bot_events += 1
                report.failures.append(
                    f"list fetch failed [{list_resp.error_kind}] {entry_url}")
                continue

            list_result = adapter.parse_list(
                list_resp.body.decode("utf-8", errors="replace"),
                list_resp.final_url,
            )
            for detail_url in list_result.detail_links:
                fp = _url_fp(detail_url)
                self.metadata.upsert_url_record(
                    task_id=self.task.task_id, url_fp=fp, url=detail_url,
                    host=self.seed.host, depth=1, parent_url_fp=None,
                    discovery_source="list_page",
                )
                if self.frontier.submit(FrontierItem(
                    url=detail_url, url_fp=fp, host=self.seed.host,
                    depth=1, parent_url_fp=None, discovery_source="list_page",
                    priority_score=0.5,
                )):
                    report.detail_urls_discovered += 1

        # 3. 循环抓详情
        while True:
            item = self.frontier.next_ready()
            if item is None:
                break
            allowed, _ = self.robots.is_allowed(item.url)
            if not allowed:
                logger.info("robots disallow %s", item.url)
                continue
            self._fetch_and_sink_detail(item, adapter, report)

        return report

    # ─── 单详情页处理 ────────────────────────────────────

    def _fetch_and_sink_detail(self, item: FrontierItem, adapter, report: RunReport) -> None:
        resp: HttpResponse = self.http.fetch(item.url, host=item.host)
        report.detail_urls_fetched += 1

        self.metadata.insert_fetch_record(
            task_id=self.task.task_id, url_fp=item.url_fp,
            attempt=resp.attempts,
            status_code=resp.status_code or None,
            content_type=resp.headers.get("content-type"),
            bytes_received=len(resp.body) if resp.body else None,
            latency_ms=resp.elapsed_ms,
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
            error_kind=resp.error_kind,
            error_detail=resp.error_detail,
        )

        if resp.error_kind:
            report.errors += 1
            if resp.anti_bot_signal:
                report.anti_bot_events += 1
            report.failures.append(
                f"detail fetch failed [{resp.error_kind}] {item.url}")
            return

        # 解析
        try:
            detail = adapter.parse_detail(
                resp.body.decode("utf-8", errors="replace"),
                resp.final_url,
            )
        except Exception as e:  # noqa: BLE001
            report.errors += 1
            report.failures.append(f"parse failed {item.url}: {e}")
            return

        # 计算指纹
        url_hash = hashlib.sha256(item.url.encode("utf-8")).hexdigest()
        body_sha = _content_sha256(detail.body_text)

        # 写 blob
        key = _blob_key(self.task.task_id, url_hash[:16])
        blob_uri = self.blobs.put(key, resp.body, content_type=resp.headers.get("content-type"))

        # 写 crawl_raw（按 url_hash 去重）
        data_payload = {
            "title": detail.title,
            "body_text": detail.body_text[:50000],  # 安全上限
            "source_metadata": detail.source_metadata.raw,
            "attachments": [
                {"url": a.url, "filename": a.filename, "mime": a.mime}
                for a in detail.attachments
            ],
            "raw_links_count": len(detail.raw_links),
        }
        inserted = self.metadata.insert_crawl_raw(
            task_id=self.task.task_id,
            business_context=self.task.business_context,
            host=item.host,
            url=item.url,
            canonical_url=resp.final_url,
            url_hash=url_hash,
            content_sha256=body_sha,
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
