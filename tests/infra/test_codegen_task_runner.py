from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from infra.storage.sqlite_store import SqliteMetadataStore
from scripts.run_codegen_for_adapter import (
    apply_db_task_to_args,
    claim_codegen_task,
    mark_codegen_task_finished,
)


def _init_db(path: Path) -> None:
    store = SqliteMetadataStore(path)
    store.init_schema()
    store.close()


def _insert_task(
    db: Path,
    *,
    site_url: str,
    host: str,
    data_kind: str = "policy",
    priority: int = 5,
) -> int:
    conn = sqlite3.connect(db)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO crawl_task
                (business_context, task_type, site_url, host, data_kind,
                 scope_mode, crawl_mode, max_pages_per_run, politeness_rps,
                 priority, scope_description)
                VALUES ('gov_policy', 'create', ?, ?, ?, 'same_origin',
                        'full', 30, 0.3, ?, 'from test')""",
                (site_url, host, data_kind, priority),
            )
            task_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO crawl_task_execution (task_id, status) VALUES (?, 'scheduled')",
                (task_id,),
            )
            return task_id
    finally:
        conn.close()


def test_claim_codegen_task_claims_next_scheduled_by_priority(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    low = _insert_task(
        db,
        site_url="https://low.example.com/policy/",
        host="low.example.com",
        priority=5,
    )
    high = _insert_task(
        db,
        site_url="https://high.example.com/policy/",
        host="high.example.com",
        data_kind="news",
        priority=1,
    )

    task = claim_codegen_task(db, task_id=None, worker_id="worker-a")

    assert task is not None
    assert task.task_id == high
    assert task.host == "high.example.com"
    assert task.data_kind == "news"

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT task_id, status, worker_id, adapter_host FROM crawl_task_execution "
            "ORDER BY task_id"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        (low, "scheduled", None, None),
        (high, "running", "worker-a", "high.example.com"),
    ]


def test_claim_codegen_task_can_claim_specific_task_id(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    first = _insert_task(
        db,
        site_url="https://first.example.com/policy/",
        host="first.example.com",
        priority=1,
    )
    second = _insert_task(
        db,
        site_url="https://second.example.com/policy/",
        host="second.example.com",
        priority=9,
    )

    task = claim_codegen_task(db, task_id=second, worker_id="worker-b")

    assert task is not None
    assert task.task_id == second
    assert task.task_id != first


def test_apply_db_task_to_args_sets_codegen_inputs(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(
        db,
        site_url="https://www.example.gov.cn/xxgk/",
        host="www.example.gov.cn",
    )
    task = claim_codegen_task(db, task_id=task_id, worker_id="worker-c")
    assert task is not None
    args = argparse.Namespace(smoke_task_id=None)

    apply_db_task_to_args(args, task)

    assert args.codegen_task_id == task_id
    assert args.host == "www.example.gov.cn"
    assert args.entry_url == "https://www.example.gov.cn/xxgk/"
    assert args.business_context == "gov_policy"
    assert args.scope_mode == "same_origin"
    assert args.smoke_task_id == task_id


def test_mark_codegen_task_finished_updates_status_and_counters(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(
        db,
        site_url="https://www.example.gov.cn/xxgk/",
        host="www.example.gov.cn",
    )
    assert claim_codegen_task(db, task_id=task_id, worker_id="worker-d") is not None

    mark_codegen_task_finished(
        db,
        task_id=task_id,
        success=True,
        branch="agent/feature-20260429-codegen-example-t1",
        worker_id="worker-d",
    )

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            """SELECT status, last_run_id, last_run_status, run_count,
            consecutive_failures, worker_id
            FROM crawl_task_execution WHERE task_id=?""",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "completed",
        "agent/feature-20260429-codegen-example-t1",
        "green",
        1,
        0,
        "worker-d",
    )
