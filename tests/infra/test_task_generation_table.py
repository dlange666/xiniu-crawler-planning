"""crawl_task_generation 表生命周期测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from infra.codegen.task_db import (
    claim_codegen_task,
    mark_codegen_drafting,
    mark_codegen_task_finished,
)
from infra.storage.sqlite_store import SqliteMetadataStore


def _init_db(path: Path) -> None:
    store = SqliteMetadataStore(path)
    store.init_schema()
    store.close()


def _insert_task(db: Path, *, host: str = "www.example.gov.cn") -> int:
    conn = sqlite3.connect(db)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO crawl_task
                (business_context, task_type, site_url, host, data_kind,
                 scope_mode, crawl_mode, max_pages_per_run, politeness_rps,
                 priority, scope_description)
                VALUES ('gov_policy', 'create', ?, ?, 'policy', 'same_origin',
                        'full', 30, 1.0, 5, 'from test')""",
                (f"https://{host}/", host),
            )
            task_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO crawl_task_execution (task_id, status) VALUES (?, 'scheduled')",
                (task_id,),
            )
            conn.execute(
                "INSERT INTO crawl_task_generation (task_id, status) VALUES (?, 'pending')",
                (task_id,),
            )
            return task_id
    finally:
        conn.close()


def _generation_row(db: Path, task_id: int) -> dict | None:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM crawl_task_generation WHERE task_id=?", (task_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_init_schema_backfills_pending_for_existing_tasks(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(db)

    # 第一次 init_schema 已建表；插 task 时 webui store 才会插 generation 行。
    # 这里直接走 raw INSERT 模拟"老 task 没有 generation 行"，再次 init_schema 应 backfill。
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute("DELETE FROM crawl_task_generation WHERE task_id=?", (task_id,))
    finally:
        conn.close()
    assert _generation_row(db, task_id) is None

    SqliteMetadataStore(db).init_schema()
    row = _generation_row(db, task_id)
    assert row is not None
    assert row["status"] == "pending"


def test_claim_codegen_task_advances_to_claimed(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(db, host="www.foo.gov.cn")

    task = claim_codegen_task(db, task_id=task_id, worker_id="worker-1")
    assert task is not None

    row = _generation_row(db, task_id)
    assert row is not None
    assert row["status"] == "claimed"
    assert row["worker_id"] == "worker-1"
    assert row["claim_at"] is not None
    assert row["attempts"] == 1


def test_mark_drafting_only_advances_from_claim_states(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(db)

    # pending 不应被推到 drafting（claim 才能推）
    mark_codegen_drafting(db, task_id=task_id)
    assert _generation_row(db, task_id)["status"] == "pending"

    claim_codegen_task(db, task_id=task_id, worker_id="w")
    mark_codegen_drafting(db, task_id=task_id)
    assert _generation_row(db, task_id)["status"] == "drafting"


def test_mark_finished_writes_merged_or_failed(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(db)
    claim_codegen_task(db, task_id=task_id, worker_id="w")

    eval_path = tmp_path / "eval.md"
    mark_codegen_task_finished(
        db,
        task_id=task_id,
        success=True,
        branch="agent/feature-x",
        worker_id="w",
        eval_path=eval_path,
    )
    row = _generation_row(db, task_id)
    assert row["status"] == "merged"
    assert row["branch"] == "agent/feature-x"
    assert row["last_eval_path"] == str(eval_path)
    assert row["last_error"] is None
    assert row["finished_at"] is not None

    # 第二次跑（失败）：状态回到 failed，error 写入
    claim_codegen_task(db, task_id=task_id, worker_id="w2")
    mark_codegen_task_finished(
        db,
        task_id=task_id,
        success=False,
        branch="agent/feature-x",
        worker_id="w2",
        eval_path=eval_path,
        failed_gates=["pytest_new", "audit"],
    )
    row = _generation_row(db, task_id)
    assert row["status"] == "failed"
    assert "pytest_new" in row["last_error"]
    assert "audit" in row["last_error"]


def test_re_claim_increments_attempts(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    _init_db(db)
    task_id = _insert_task(db)

    claim_codegen_task(db, task_id=task_id, worker_id="w1")
    # 模拟 reset 到 scheduled 再次 claim
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute("UPDATE crawl_task_execution SET status='scheduled' WHERE task_id=?", (task_id,))
    finally:
        conn.close()
    claim_codegen_task(db, task_id=task_id, worker_id="w2")

    row = _generation_row(db, task_id)
    assert row["attempts"] == 2
    assert row["worker_id"] == "w2"
