"""crawl_task / crawl_task_execution 的 claim 与 finish。"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from infra.storage.sqlite_store import SqliteMetadataStore


@dataclass(frozen=True)
class CodegenDbTask:
    task_id: int
    business_context: str
    site_url: str
    host: str
    data_kind: str
    scope_mode: str
    scope_url_pattern: str | None
    max_pages_per_run: int | None
    politeness_rps: float
    scope_description: str | None


_SELECT_COLUMNS = """t.task_id, t.business_context, t.site_url, t.host, t.data_kind,
                t.scope_mode, t.scope_url_pattern, t.max_pages_per_run,
                t.politeness_rps, t.scope_description"""


def claim_codegen_task(
    db_path: Path,
    *,
    task_id: int | None,
    worker_id: str,
) -> CodegenDbTask | None:
    """认领一条 scheduled crawl_task。

    SQLite 没有 SKIP LOCKED，dev runner 用 BEGIN IMMEDIATE 串行化 claim。
    完整外部 TaskSource 后续可换成自身的锁原语。
    """
    schema = SqliteMetadataStore(db_path)
    schema.init_schema()
    schema.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        where = ["COALESCE(e.status, 'scheduled') = 'scheduled'"]
        params: list[object] = []
        if task_id is None:
            where.append(
                "(e.next_run_at IS NULL "
                "OR e.next_run_at <= strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            )
            order = "ORDER BY t.priority ASC, t.created_at ASC, t.task_id ASC LIMIT 1"
        else:
            where.append("t.task_id = ?")
            params.append(task_id)
            order = ""

        sql = f"""SELECT {_SELECT_COLUMNS}
            FROM crawl_task t
            LEFT JOIN crawl_task_execution e ON e.task_id = t.task_id
            WHERE {' AND '.join(where)}
            {order}"""
        row = conn.execute(sql, params).fetchone()

        if row is None:
            conn.rollback()
            return None

        conn.execute(
            """INSERT INTO crawl_task_execution
            (task_id, status, adapter_host, worker_id, claim_at, heartbeat_at)
            VALUES (?, 'running', ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(task_id) DO UPDATE SET
                status='running',
                adapter_host=excluded.adapter_host,
                worker_id=excluded.worker_id,
                claim_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
            (int(row["task_id"]), row["host"], worker_id),
        )
        # Codegen 过程状态：claim → claimed（spec data-model.md §4.1.2）。
        # invoke_opencode 后 wrapper 会再 advance 到 drafting / merged / failed。
        conn.execute(
            """INSERT INTO crawl_task_generation
            (task_id, status, worker_id, claim_at, heartbeat_at, attempts, started_at)
            VALUES (?, 'claimed', ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    strftime('%Y-%m-%dT%H:%M:%fZ','now'), 1,
                    strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(task_id) DO UPDATE SET
                status='claimed',
                worker_id=excluded.worker_id,
                claim_at=excluded.claim_at,
                heartbeat_at=excluded.heartbeat_at,
                attempts=crawl_task_generation.attempts + 1,
                started_at=excluded.started_at,
                last_error=NULL,
                finished_at=NULL""",
            (int(row["task_id"]), worker_id),
        )
        conn.commit()
        return CodegenDbTask(
            task_id=int(row["task_id"]),
            business_context=str(row["business_context"]),
            site_url=str(row["site_url"]),
            host=str(row["host"]),
            data_kind=str(row["data_kind"]),
            scope_mode=str(row["scope_mode"]),
            scope_url_pattern=row["scope_url_pattern"],
            max_pages_per_run=row["max_pages_per_run"],
            politeness_rps=float(row["politeness_rps"]),
            scope_description=row["scope_description"],
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_db_task_to_args(args: argparse.Namespace, task: CodegenDbTask) -> None:
    args.codegen_task_id = task.task_id
    args.host = task.host
    args.entry_url = task.site_url
    args.business_context = task.business_context
    args.data_kind = task.data_kind
    args.scope_mode = task.scope_mode
    args.scope_url_pattern = task.scope_url_pattern
    args.max_pages_per_run = task.max_pages_per_run
    args.politeness_rps = task.politeness_rps
    args.scope_description = task.scope_description
    if args.smoke_task_id is None:
        args.smoke_task_id = task.task_id


def mark_codegen_task_finished(
    db_path: Path,
    *,
    task_id: int,
    success: bool,
    branch: str,
    worker_id: str,
    eval_path: Path | None = None,
    failed_gates: list[str] | None = None,
) -> None:
    status = "completed" if success else "failed"
    run_status = "green" if success else "red"
    error_kind = None if success else "codegen_gate_failed"
    error_detail = None
    if not success:
        gates = ", ".join(failed_gates or ["unknown"])
        error_detail = f"wrapper gates failed: {gates}"
    generation_status = "merged" if success else "failed"
    eval_path_str = str(eval_path) if eval_path else None
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                """UPDATE crawl_task_execution SET
                    status=?,
                    last_run_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    last_run_id=?,
                    last_run_status=?,
                    run_count=run_count + 1,
                    consecutive_failures=CASE WHEN ? THEN 0 ELSE consecutive_failures + 1 END,
                    worker_id=?,
                    heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    last_error_kind=?,
                    last_error_detail=?,
                    last_eval_path=?,
                    needs_manual_review=?
                WHERE task_id=?""",
                (
                    status,
                    branch,
                    run_status,
                    1 if success else 0,
                    worker_id,
                    error_kind,
                    error_detail,
                    eval_path_str,
                    0 if success else 1,
                    task_id,
                ),
            )
            # Codegen 过程状态写 merged/failed；spec §4.1.2。
            conn.execute(
                """UPDATE crawl_task_generation SET
                    status=?,
                    branch=?,
                    last_error=?,
                    last_eval_path=?,
                    finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE task_id=?""",
                (
                    generation_status,
                    branch,
                    error_detail,
                    eval_path_str,
                    task_id,
                ),
            )
    finally:
        conn.close()


def mark_codegen_drafting(db_path: Path, *, task_id: int) -> None:
    """invoke_opencode 前把 generation 状态推到 drafting。"""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                """UPDATE crawl_task_generation SET
                    status='drafting',
                    heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE task_id=? AND status IN ('claimed','drafting')""",
                (task_id,),
            )
    finally:
        conn.close()
