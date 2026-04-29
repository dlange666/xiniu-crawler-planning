#!/usr/bin/env python3
"""Ingest PRD data-source URLs into the local crawl_task database.

This script is intentionally offline: it only parses the archived PRD Markdown
and writes task rows to local SQLite. Actual fetching still belongs to the
crawler runner so robots, rate limits, raw retention, and anti-bot handling stay
centralized.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra.storage.sqlite_store import SqliteMetadataStore  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PRD = REPO / "docs/prd/policy-data-sources-phase1-20260427.md"
DEFAULT_DB = REPO / "runtime/db/dev.db"
URL_RE = re.compile(r"https?://[^\s<>'\"（）)\]】,，;；]+")


@dataclass(frozen=True)
class PrdTaskCandidate:
    site_url: str
    host: str
    data_kind: str
    scope_description: str
    source_line: int


@dataclass(frozen=True)
class IngestSummary:
    source: str
    db: str | None
    candidates: int
    inserted: int
    skipped_existing: int
    skipped_invalid: int
    dry_run: bool


def extract_candidates(prd_path: Path) -> list[PrdTaskCandidate]:
    headings: list[str] = []
    candidates: list[PrdTaskCandidate] = []
    seen: set[str] = set()

    for line_no, raw_line in enumerate(prd_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            headings = headings[: level - 1]
            headings.append(title)

        urls = [clean_url(m.group(0)) for m in URL_RE.finditer(line)]
        for url in urls:
            host = urlparse(url).netloc.lower()
            if not host or url in seen:
                continue
            seen.add(url)
            label = line.replace(url, " ").strip()
            context = " / ".join([*headings[-4:], label]).strip(" /")
            candidates.append(
                PrdTaskCandidate(
                    site_url=url,
                    host=host,
                    data_kind=infer_data_kind(context),
                    scope_description=context,
                    source_line=line_no,
                )
            )
    return candidates


def clean_url(url: str) -> str:
    return url.strip().rstrip(".。；;，,、")


def infer_data_kind(context: str) -> str:
    text = context.lower()
    if "政策解读" in context or "解读" in context:
        return "policy_interpretation"
    if "新闻" in context or "要闻" in context or "动态" in context:
        return "news"
    if "公告通知" in context or "通知公告" in context or "公告" in context:
        return "announcement"
    if "规划" in context:
        return "planning"
    if "法律法规" in context or "规章" in context or "规则" in context or "rule" in text:
        return "regulation"
    return "policy"


def ingest_candidates(
    db_path: Path,
    candidates: list[PrdTaskCandidate],
    *,
    actor: str,
    purpose: str,
    legal_basis: str,
    responsible_party: str,
    max_pages_per_run: int,
    politeness_rps: float,
    dry_run: bool,
) -> IngestSummary:
    if dry_run:
        return IngestSummary(
            source="",
            db=str(db_path),
            candidates=len(candidates),
            inserted=0,
            skipped_existing=0,
            skipped_invalid=0,
            dry_run=True,
        )

    schema = SqliteMetadataStore(db_path)
    schema.init_schema()
    schema.close()

    inserted = 0
    skipped_existing = 0
    skipped_invalid = 0
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            for candidate in candidates:
                if not candidate.host:
                    skipped_invalid += 1
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM crawl_task WHERE site_url=? LIMIT 1",
                    (candidate.site_url,),
                ).fetchone()
                if exists:
                    skipped_existing += 1
                    continue
                cur = conn.execute(
                    """INSERT INTO crawl_task
                    (business_context, task_type, site_url, host, data_kind,
                     scope_description, scope_mode, crawl_mode, max_pages_per_run,
                     politeness_rps, purpose, legal_basis, responsible_party,
                     created_by)
                    VALUES (
                     'gov_policy', 'create', ?, ?, ?, ?,
                     'same_origin', 'full', ?, ?, ?, ?, ?, ?
                    )""",
                    (
                        candidate.site_url,
                        candidate.host,
                        candidate.data_kind,
                        candidate.scope_description,
                        max_pages_per_run,
                        politeness_rps,
                        purpose,
                        legal_basis,
                        responsible_party,
                        actor,
                    ),
                )
                task_id = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO crawl_task_execution
                    (task_id, status, adapter_host)
                    VALUES (?, 'scheduled', ?)""",
                    (task_id, candidate.host),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO crawl_task_generation (task_id, status)
                    VALUES (?, 'pending')""",
                    (task_id,),
                )
                inserted += 1
    finally:
        conn.close()

    return IngestSummary(
        source="",
        db=str(db_path),
        candidates=len(candidates),
        inserted=inserted,
        skipped_existing=skipped_existing,
        skipped_invalid=skipped_invalid,
        dry_run=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_PRD)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("CRAWLER_DB_PATH", DEFAULT_DB)),
        help="SQLite DB path; defaults to CRAWLER_DB_PATH or runtime/db/dev.db",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--actor", default="prd-ingest")
    parser.add_argument("--responsible-party", default="crawler-team")
    parser.add_argument(
        "--purpose",
        default="第一阶段政策图谱数据源收录，用于后续合规采集任务排期。",
    )
    parser.add_argument(
        "--legal-basis",
        default="公开网页数据源目录归档；实际采集仍遵守 robots 与站点限速。",
    )
    parser.add_argument("--max-pages-per-run", type=int, default=30)
    parser.add_argument("--politeness-rps", type=float, default=0.3)
    args = parser.parse_args()

    candidates = extract_candidates(args.source)
    summary = ingest_candidates(
        args.db,
        candidates,
        actor=args.actor,
        purpose=args.purpose,
        legal_basis=args.legal_basis,
        responsible_party=args.responsible_party,
        max_pages_per_run=args.max_pages_per_run,
        politeness_rps=args.politeness_rps,
        dry_run=args.dry_run,
    )
    summary = IngestSummary(
        source=str(args.source),
        db=str(args.db) if not args.dry_run else None,
        candidates=summary.candidates,
        inserted=summary.inserted,
        skipped_existing=summary.skipped_existing,
        skipped_invalid=summary.skipped_invalid,
        dry_run=summary.dry_run,
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
