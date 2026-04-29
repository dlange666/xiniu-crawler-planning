"""Task and result queries for WebUI."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from infra.storage.sqlite_store import SqliteMetadataStore

UrlKind = Literal["all", "collected", "uncollected", "fetched", "jump"]


class TaskStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        schema = SqliteMetadataStore(db_path)
        schema.init_schema()
        schema.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_task(self, data: dict[str, Any], *, actor: str) -> int:
        site_url = str(data["site_url"]).strip()
        host = urlparse(site_url).netloc
        if not host:
            raise ValueError("site_url must include a host")

        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    """INSERT INTO crawl_task
                    (business_context, task_type, site_url, host, data_kind,
                     scope_mode, scope_url_pattern, crawl_mode, max_pages_per_run,
                     politeness_rps, purpose, responsible_party, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        data.get("business_context", "gov_policy"),
                        data.get("task_type", "create"),
                        site_url,
                        host,
                        data.get("data_kind", "policy"),
                        data.get("scope_mode", "same_origin"),
                        data.get("scope_url_pattern") or None,
                        data.get("crawl_mode", "full"),
                        _optional_int(data.get("max_pages_per_run")),
                        float(data.get("politeness_rps") or 1.0),
                        data.get("purpose") or None,
                        data.get("responsible_party") or None,
                        actor,
                    ),
                )
                task_id = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO crawl_task_execution
                    (task_id, status, adapter_host)
                    VALUES (?, 'scheduled', ?)""",
                    (task_id, host),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO crawl_task_generation (task_id, status)
                    VALUES (?, 'pending')""",
                    (task_id,),
                )
            return task_id
        finally:
            conn.close()

    def list_tasks(
        self,
        *,
        status: str | None = None,
        business_context: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if status:
            where.append("COALESCE(e.status, 'scheduled') = ?")
            params.append(status)
        if business_context:
            where.append("t.business_context = ?")
            params.append(business_context)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        params.extend([limit, offset])
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""SELECT
                    t.task_id, t.business_context, t.site_url, t.host, t.data_kind,
                    t.crawl_mode, t.scope_mode, t.max_pages_per_run,
                    t.politeness_rps, t.created_by, t.created_at,
                    COALESCE(e.status, 'scheduled') AS status,
                    COALESCE(g.status, 'pending') AS generation_status,
                    COALESCE(raw.raw_count, 0) AS raw_count,
                    COALESCE(urls.url_count, 0) AS url_count,
                    COALESCE(fetches.fetch_count, 0) AS fetch_count
                FROM crawl_task t
                LEFT JOIN crawl_task_execution e ON e.task_id = t.task_id
                LEFT JOIN crawl_task_generation g ON g.task_id = t.task_id
                LEFT JOIN (
                    SELECT task_id, COUNT(*) AS raw_count
                    FROM crawl_raw GROUP BY task_id
                ) raw ON raw.task_id = t.task_id
                LEFT JOIN (
                    SELECT task_id, COUNT(*) AS url_count
                    FROM url_record GROUP BY task_id
                ) urls ON urls.task_id = t.task_id
                LEFT JOIN (
                    SELECT task_id, COUNT(*) AS fetch_count
                    FROM fetch_record GROUP BY task_id
                ) fetches ON fetches.task_id = t.task_id
                {where_sql}
                ORDER BY t.created_at DESC, t.task_id DESC
                LIMIT ? OFFSET ?""",
                tuple(params),
            ).fetchall()
            return [_row_dict(r) for r in rows]
        finally:
            conn.close()

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT t.*, COALESCE(e.status, 'scheduled') AS status,
                   e.last_run_at, e.last_run_id, e.last_run_status, e.run_count,
                   e.consecutive_failures
                FROM crawl_task t
                LEFT JOIN crawl_task_execution e ON e.task_id = t.task_id
                WHERE t.task_id = ?""",
                (task_id,),
            ).fetchone()
            return _row_dict(row) if row else None
        finally:
            conn.close()

    def cancel_task(self, task_id: int) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO crawl_task_execution (task_id, status)
                    VALUES (?, 'disabled')
                    ON CONFLICT(task_id) DO UPDATE SET status='disabled'""",
                    (task_id,),
                )
        finally:
            conn.close()

    def progress(self, task_id: int) -> dict[str, int]:
        conn = self._connect()
        try:
            states = {
                r["frontier_state"]: int(r["n"])
                for r in conn.execute(
                    """SELECT frontier_state, COUNT(*) AS n
                    FROM url_record WHERE task_id = ? GROUP BY frontier_state""",
                    (task_id,),
                ).fetchall()
            }
            raw_count = conn.execute(
                "SELECT COUNT(*) AS n FROM crawl_raw WHERE task_id = ?", (task_id,)
            ).fetchone()["n"]
            states["raw"] = int(raw_count)
            return states
        finally:
            conn.close()

    def timeseries(self, task_id: int) -> dict[str, Any]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT substr(fetched_at, 1, 16) AS bucket, COUNT(*) AS n
                FROM fetch_record
                WHERE task_id = ?
                GROUP BY bucket
                ORDER BY bucket ASC
                LIMIT 120""",
                (task_id,),
            ).fetchall()
            labels = [r["bucket"] for r in rows]
            values = [int(r["n"]) for r in rows]
            return {"labels": labels, "series": [{"name": "fetches", "values": values}]}
        finally:
            conn.close()

    def list_url_records(
        self,
        task_id: int,
        *,
        kind: UrlKind = "all",
        depth: int | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where_sql, params = _url_filter_sql(task_id, kind=kind, depth=depth)
        params.extend([limit, offset])
        order_sql = _url_order_sql(kind)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""SELECT
                    u.url_fp, u.url, u.host, u.depth, u.parent_url_fp,
                    u.discovery_source, u.frontier_state, u.scope_decision,
                    u.attempts, u.created_at, u.updated_at,
                    fr.status_code, fr.error_kind, fr.fetched_at,
                    cr.id AS raw_id, cr.data AS raw_data, cr.created_at AS raw_created_at
                FROM url_record u
                LEFT JOIN (
                    SELECT f1.*
                    FROM fetch_record f1
                    JOIN (
                        SELECT task_id, url_fp, MAX(attempt) AS max_attempt
                        FROM fetch_record
                        WHERE task_id = ?
                        GROUP BY task_id, url_fp
                    ) latest
                      ON latest.task_id = f1.task_id
                     AND latest.url_fp = f1.url_fp
                     AND latest.max_attempt = f1.attempt
                ) fr ON fr.task_id = u.task_id AND fr.url_fp = u.url_fp
                LEFT JOIN crawl_raw cr
                  ON cr.task_id = u.task_id
                 AND (cr.url = u.url OR cr.canonical_url = u.canonical_url)
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?""",
                (task_id, *params),
            ).fetchall()
            return [_url_record_dict(r) for r in rows]
        finally:
            conn.close()

    def count_url_records(
        self, task_id: int, *, kind: UrlKind = "all", depth: int | None = None
    ) -> int:
        where_sql, params = _url_filter_sql(task_id, kind=kind, depth=depth)
        conn = self._connect()
        try:
            row = conn.execute(
                f"""SELECT COUNT(*) AS n
                FROM url_record u
                LEFT JOIN (
                    SELECT f1.*
                    FROM fetch_record f1
                    JOIN (
                        SELECT task_id, url_fp, MAX(attempt) AS max_attempt
                        FROM fetch_record
                        WHERE task_id = ?
                        GROUP BY task_id, url_fp
                    ) latest
                      ON latest.task_id = f1.task_id
                     AND latest.url_fp = f1.url_fp
                     AND latest.max_attempt = f1.attempt
                ) fr ON fr.task_id = u.task_id AND fr.url_fp = u.url_fp
                LEFT JOIN crawl_raw cr
                  ON cr.task_id = u.task_id
                 AND (cr.url = u.url OR cr.canonical_url = u.canonical_url)
                {where_sql}""",
                (task_id, *params),
            ).fetchone()
            return int(row["n"]) if row else 0
        finally:
            conn.close()

    def depth_summary(self, task_id: int, *, kind: UrlKind = "all") -> list[dict[str, int]]:
        where_sql, params = _url_filter_sql(task_id, kind=kind)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""SELECT depth, COUNT(*) AS url_count
                FROM url_record u
                LEFT JOIN (
                    SELECT f1.*
                    FROM fetch_record f1
                    JOIN (
                        SELECT task_id, url_fp, MAX(attempt) AS max_attempt
                        FROM fetch_record
                        WHERE task_id = ?
                        GROUP BY task_id, url_fp
                    ) latest
                      ON latest.task_id = f1.task_id
                     AND latest.url_fp = f1.url_fp
                     AND latest.max_attempt = f1.attempt
                ) fr ON fr.task_id = u.task_id AND fr.url_fp = u.url_fp
                LEFT JOIN crawl_raw cr
                  ON cr.task_id = u.task_id
                 AND (cr.url = u.url OR cr.canonical_url = u.canonical_url)
                {where_sql}
                GROUP BY depth
                ORDER BY depth ASC""",
                (task_id, *params),
            ).fetchall()
            return [{"depth": int(r["depth"]), "url_count": int(r["url_count"])} for r in rows]
        finally:
            conn.close()

    def list_items(self, task_id: int, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT id, task_id, business_context, host, url, raw_blob_uri,
                   data, created_at
                FROM crawl_raw
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?""",
                (task_id, limit, offset),
            ).fetchall()
            return [_item_dict(r) for r in rows]
        finally:
            conn.close()

    def get_item(self, task_id: int, item_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM crawl_raw WHERE task_id = ? AND id = ?",
                (task_id, item_id),
            ).fetchone()
            if row is None:
                return None
            item = _item_dict(row)
            item["child_links"] = self._child_links(conn, task_id=task_id, item=item)
            return item
        finally:
            conn.close()

    def _child_links(
        self, conn: sqlite3.Connection, *, task_id: int, item: dict[str, Any]
    ) -> list[dict[str, Any]]:
        parent_fp = hashlib.sha256(str(item["url"]).encode("utf-8")).hexdigest()[:32]
        rows = conn.execute(
            """SELECT
                u.url, u.depth, u.discovery_source, u.frontier_state,
                fr.status_code, fr.error_kind, cr.id AS raw_id
            FROM url_record u
            LEFT JOIN (
                SELECT f1.*
                FROM fetch_record f1
                JOIN (
                    SELECT task_id, url_fp, MAX(attempt) AS max_attempt
                    FROM fetch_record
                    WHERE task_id = ?
                    GROUP BY task_id, url_fp
                ) latest
                  ON latest.task_id = f1.task_id
                 AND latest.url_fp = f1.url_fp
                 AND latest.max_attempt = f1.attempt
            ) fr ON fr.task_id = u.task_id AND fr.url_fp = u.url_fp
            LEFT JOIN crawl_raw cr
              ON cr.task_id = u.task_id
             AND (cr.url = u.url OR cr.canonical_url = u.canonical_url)
            WHERE u.task_id = ? AND u.parent_url_fp = ?
            ORDER BY u.depth ASC, u.created_at ASC, u.url_fp ASC""",
            (task_id, task_id, parent_fp),
        ).fetchall()

        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            link = _row_dict(row)
            link["link_type"] = _child_link_type(link.get("discovery_source"), str(link["url"]))
            links.append(link)
            seen.add(str(link["url"]))

        for attachment in item.get("attachments") or []:
            url = str(attachment.get("url") or "")
            if not url or url in seen:
                continue
            links.append(
                {
                    "url": url,
                    "depth": None,
                    "discovery_source": "detail_to_attachment",
                    "frontier_state": "discovered",
                    "status_code": None,
                    "error_kind": None,
                    "raw_id": None,
                    "link_type": "attachment",
                    "filename": attachment.get("filename"),
                    "mime": attachment.get("mime"),
                }
            )
            seen.add(url)

        for url in item.get("interpret_links") or []:
            url = str(url)
            if not url or url in seen:
                continue
            links.append(_raw_child_link(url, "detail_to_interpret", "interpret"))
            seen.add(url)

        for url in item.get("raw_links") or []:
            url = str(url)
            if not url or url in seen:
                continue
            links.append(_raw_child_link(url, "detail_raw_link", _child_link_type(None, url)))
            seen.add(url)

        return links


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row), strict=True))


def _item_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = _row_dict(row)
    data = json.loads(out.get("data") or "{}")
    out["title"] = data.get("title") or "(no title)"
    out["body_text"] = data.get("body_text") or ""
    out["source_metadata"] = data.get("source_metadata") or {}
    out["attachments"] = data.get("attachments") or []
    out["interpret_links"] = data.get("interpret_links") or []
    out["raw_links"] = data.get("raw_links") or []
    return out


def _url_record_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = _row_dict(row)
    raw_data = out.pop("raw_data", None)
    has_fetch = out.get("status_code") is not None or out.get("error_kind") or out.get("fetched_at")
    out["link_kind"] = "fetched" if has_fetch or out.get("raw_id") else "jump"
    if raw_data:
        data = json.loads(raw_data)
        out["raw_title"] = data.get("title") or "(no title)"
        out["raw_excerpt"] = (data.get("body_text") or "")[:180]
    else:
        out["raw_title"] = None
        out["raw_excerpt"] = None
    return out


def _url_filter_sql(
    task_id: int, *, kind: UrlKind, depth: int | None = None
) -> tuple[str, list[Any]]:
    if kind not in {"all", "collected", "uncollected", "fetched", "jump"}:
        raise ValueError(f"unsupported url kind: {kind}")

    where = ["u.task_id = ?"]
    params: list[Any] = [task_id]
    if depth is not None:
        where.append("u.depth = ?")
        params.append(depth)
    if kind == "collected":
        where.append("cr.id IS NOT NULL")
    elif kind == "uncollected":
        where.append("cr.id IS NULL")
    elif kind == "fetched":
        where.append(
            """(
                u.frontier_state IN ('done', 'failed', 'dlq')
                OR fr.fetch_id IS NOT NULL
                OR cr.id IS NOT NULL
            )"""
        )
    elif kind == "jump":
        where.append(
            """u.frontier_state IN ('pending', 'in_flight')
            AND fr.fetch_id IS NULL
            AND cr.id IS NULL"""
        )
    return "WHERE " + " AND ".join(where), params


def _url_order_sql(kind: UrlKind) -> str:
    if kind in {"all", "collected", "fetched"}:
        return (
            "CASE WHEN cr.id IS NULL THEN 1 ELSE 0 END ASC, "
            "cr.id DESC, u.depth ASC, u.created_at ASC, u.url_fp ASC"
        )
    return "u.depth ASC, u.created_at ASC, u.url_fp ASC"


def _child_link_type(discovery_source: Any, url: str) -> str:
    source = str(discovery_source or "")
    lower = url.lower()
    if source == "detail_to_attachment" or lower.endswith(
        (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ofd")
    ):
        return "attachment"
    if source == "detail_to_interpret":
        return "interpret"
    return "link"


def _raw_child_link(url: str, discovery_source: str, link_type: str) -> dict[str, Any]:
    return {
        "url": url,
        "depth": None,
        "discovery_source": discovery_source,
        "frontier_state": "discovered",
        "status_code": None,
        "error_kind": None,
        "raw_id": None,
        "link_type": link_type,
    }
