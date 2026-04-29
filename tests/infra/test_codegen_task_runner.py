from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from infra.storage.sqlite_store import SqliteMetadataStore
from scripts.run_codegen_for_adapter import (
    GateRunResult,
    adapter_artifact,
    adapter_test_artifact,
    apply_db_task_to_args,
    claim_codegen_task,
    codegen_commit_paths,
    mark_codegen_task_finished,
    normalize_task_json,
    plan_artifact_path,
    record_wrapper_eval,
    seed_artifact,
    slug,
    source_dir,
    validate_golden_artifacts,
    write_feedback_prompt,
    write_per_task_prompt,
    write_task_skeleton,
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


def test_slug_uses_source_name_not_generic_channel_prefix() -> None:
    assert slug("www.most.gov.cn") == "most"
    assert slug("wap.miit.gov.cn") == "miit"
    assert slug("m.miit.gov.cn") == "miit"
    assert slug("search.sh.gov.cn") == "sh_search"
    assert slug("sousuo.www.gov.cn") == "gov_search"


def test_codegen_artifact_paths_use_source_directory(tmp_path: Path) -> None:
    args = argparse.Namespace(host="wap.miit.gov.cn", business_context="gov_policy")

    assert source_dir(tmp_path, args) == tmp_path / "domains/gov_policy/miit"
    assert adapter_artifact(tmp_path, args) == (
        tmp_path / "domains/gov_policy/miit/miit_adapter.py"
    )
    assert seed_artifact(tmp_path, args) == (
        tmp_path / "domains/gov_policy/miit/miit_seed.yaml"
    )
    assert adapter_test_artifact(tmp_path, args) == (
        tmp_path / "tests/gov_policy/test_miit_adapter.py"
    )


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


def test_write_task_skeleton_creates_standard_pr_task_json(tmp_path: Path) -> None:
    args = argparse.Namespace(host="www.example.gov.cn")

    task_path = write_task_skeleton(
        tmp_path,
        args,
        branch="agent/feature-20260429-codegen-example",
    )

    result = normalize_task_json(task_path)
    text = task_path.read_text(encoding="utf-8")

    assert result.ok is True
    assert result.repaired is False
    assert '"file_kind": "pr-task-file"' in text
    assert f"T-{date.today():%Y%m%d}-701" in text


def test_per_task_prompt_requires_closure_gates_and_red_probe(tmp_path: Path) -> None:
    args = argparse.Namespace(
        host="www.nfra.gov.cn",
        entry_url="https://www.nfra.gov.cn/cn/view/pages/zhengwuxinxi/zhengfuxinxi.html#1",
        business_context="gov_policy",
        scope_mode="same_origin",
        scope_description="from test",
        codegen_task_id=7,
        data_kind="policy",
        smoke_task_id=7,
    )

    prompt_path = write_per_task_prompt(tmp_path, args)
    text = prompt_path.read_text(encoding="utf-8")

    assert "## 强制收口协议" in text
    assert "rm -f runtime/db/dev.db runtime/db/dev.db-wal runtime/db/dev.db-shm" in text
    assert "scripts/run_crawl_task.py domains/gov_policy/nfra/nfra_seed.yaml" in text
    assert "--db runtime/db/dev.db" in text
    assert "## red 前必须排查" in text
    assert "parse_list(seed_response, seed_url)" in text
    assert "ADAPTER_META.list_url_pattern" in text
    assert "SourceMetadata(raw=" in text
    assert "Golden 覆盖硬规则" in text
    assert "detail_url_pattern" in text


def _write_golden_pair(
    base: Path,
    *,
    host_slug: str,
    kind: str,
    index: int,
    payload: dict,
) -> None:
    stem = f"{host_slug}_golden_{kind}_{index}"
    (base / f"{stem}.html").write_text("<html></html>", encoding="utf-8")
    (base / f"{stem}.golden.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_validate_golden_artifacts_requires_coverage_and_pairs(tmp_path: Path) -> None:
    _write_golden_pair(
        tmp_path,
        host_slug="example",
        kind="list",
        index=1,
        payload={"parse_list": {"detail_links": ["https://example.gov.cn/1.html"], "next_pages": []}},
    )
    for i in range(1, 4):
        _write_golden_pair(
            tmp_path,
            host_slug="example",
            kind="detail",
            index=i,
            payload={"parse_detail": {"title": f"title-{i}", "body_text": "正文" * 80}},
        )

    ok, message = validate_golden_artifacts(tmp_path, "example")

    assert ok is True
    assert "detail=3" in message


def test_validate_golden_artifacts_requires_pagination_pair_when_signaled(
    tmp_path: Path,
) -> None:
    _write_golden_pair(
        tmp_path,
        host_slug="example",
        kind="list",
        index=1,
        payload={
            "parse_list": {
                "detail_links": ["https://example.gov.cn/1.html"],
                "next_pages": ["https://example.gov.cn/list_2.html"],
            }
        },
    )
    for i in range(1, 4):
        _write_golden_pair(
            tmp_path,
            host_slug="example",
            kind="detail",
            index=i,
            payload={"parse_detail": {"title": f"title-{i}", "body_text": "正文" * 80}},
        )

    ok, message = validate_golden_artifacts(tmp_path, "example")

    assert ok is False
    assert "pagination signal" in message


def test_write_feedback_prompt_includes_failed_gate_evidence(tmp_path: Path) -> None:
    args = argparse.Namespace(host="www.example.gov.cn", business_context="gov_policy")
    path = write_feedback_prompt(
        tmp_path,
        args,
        GateRunResult(
            results={"pytest_new": False, "audit": False, "golden": True},
            details={
                "pytest_new": "AttributeError: SourceMetadata has no get",
                "audit": "short body (<300 chars) samples\n35 chars | 微信 | https://example.gov.cn/wx.html",
            },
        ),
        attempt=1,
    )

    text = path.read_text(encoding="utf-8")
    assert "Failed gates: pytest_new, audit" in text
    assert "SourceMetadata(raw={...})" in text
    assert "short body samples" in text


def test_codegen_commit_paths_green_includes_delivery_artifacts(tmp_path: Path) -> None:
    args = argparse.Namespace(host="www.example.gov.cn", business_context="gov_policy")
    eval_path = tmp_path / f"docs/eval-test/codegen-example-{date.today():%Y%m%d}.md"
    for path in (
        plan_artifact_path(tmp_path, args),
        tmp_path / f"docs/task/active/task-codegen-example-{date.today()}.json",
        eval_path,
        tmp_path / "domains/gov_policy/example/example_adapter.py",
        tmp_path / "tests/gov_policy/test_example_adapter.py",
        tmp_path / ".codegen-prompt.md",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    paths = codegen_commit_paths(tmp_path, args, eval_path=eval_path, overall=True)
    relative = {str(path.relative_to(tmp_path)) for path in paths}

    assert "docs/eval-test/codegen-example-" + f"{date.today():%Y%m%d}.md" in relative
    assert "domains/gov_policy/example" in relative
    assert "tests/gov_policy/test_example_adapter.py" in relative
    assert ".codegen-prompt.md" not in relative


def test_codegen_commit_paths_red_only_includes_eval(tmp_path: Path) -> None:
    args = argparse.Namespace(host="www.example.gov.cn", business_context="gov_policy")
    eval_path = tmp_path / f"docs/eval-test/codegen-example-{date.today():%Y%m%d}.md"
    adapter_path = tmp_path / "domains/gov_policy/example/example_adapter.py"
    for path in (eval_path, adapter_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    paths = codegen_commit_paths(tmp_path, args, eval_path=eval_path, overall=False)

    assert paths == [eval_path]


def test_normalize_task_json_repairs_markdown_wrapped_json(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        """Here is the task file:

```json
{
  "schema_version": "1.0",
  "file_kind": "pr-task-file",
  "description": "example",
  "pr_name": "codegen-example",
  "branch": "agent/feature-20260429-codegen-example",
  "date": "2026-04-29",
  "status_enum": ["pending", "in_progress", "verifying", "completed", "failed"],
  "tasks": [
    {
      "id": "T-20260429-701",
      "title": "[codegen/example] build adapter",
      "status": "in_progress",
      "plan_id": "plan-20260429-codegen-example",
      "dependency": [],
      "assignee": "generator",
      "last_updated": "2026-04-29T14:00:00+08:00",
      "notes": ""
    }
  ]
}
```
""",
        encoding="utf-8",
    )

    result = normalize_task_json(task_path)
    repaired = task_path.read_text(encoding="utf-8")

    assert result.ok is True
    assert result.repaired is True
    assert repaired.startswith("{\n")
    assert "```" not in repaired


def test_normalize_task_json_skips_non_json_brace_before_task(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        """The previous attempt had {not json}.

{
  "schema_version": "1.0",
  "file_kind": "pr-task-file",
  "description": "example",
  "pr_name": "codegen-example",
  "branch": "agent/feature-20260429-codegen-example",
  "date": "2026-04-29",
  "status_enum": ["pending", "in_progress", "verifying", "completed", "failed"],
  "tasks": [
    {
      "id": "T-20260429-701",
      "title": "[codegen/example] build adapter",
      "status": "in_progress",
      "plan_id": "plan-20260429-codegen-example",
      "dependency": [],
      "assignee": "generator",
      "last_updated": "2026-04-29T14:00:00+08:00",
      "notes": ""
    }
  ]
}
""",
        encoding="utf-8",
    )

    result = normalize_task_json(task_path)

    assert result.ok is True
    assert result.repaired is True


def test_normalize_task_json_rejects_nonstandard_json(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        """{
  "schema_version": "1.0",
  "file_kind": "pr-task-file",
  "description": "example",
  "pr_name": "codegen-example",
  "branch": "agent/feature-20260429-codegen-example",
  "date": "2026-04-29",
  "status_enum": ["pending", "in_progress"],
  "tasks": [],
}
""",
        encoding="utf-8",
    )

    result = normalize_task_json(task_path)

    assert result.ok is False
    assert result.error is not None


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


def test_record_wrapper_eval_creates_red_eval_when_missing(tmp_path: Path) -> None:
    args = argparse.Namespace(host="www.example.gov.cn")
    log_file = tmp_path / "runtime/codegen/example.log"

    eval_path = record_wrapper_eval(
        worktree=tmp_path,
        args=args,
        branch="agent/feature-20260429-codegen-example-t1",
        log_file=log_file,
        opencode_rc=1,
        gates={"pytest_all": True, "audit": False},
        overall=False,
    )

    assert eval_path.parent == tmp_path / "docs/eval-test"
    assert eval_path.name.startswith("codegen-example-")
    assert eval_path.exists()
    text = eval_path.read_text(encoding="utf-8")
    assert "> **判定**：`red`" in text
    assert "| audit | FAIL |" in text
    assert "| opencode_exit_code | `1` |" in text
    assert "| failed_gates | `audit` |" in text


def test_record_wrapper_eval_appends_to_existing_eval(tmp_path: Path) -> None:
    args = argparse.Namespace(host="www.example.gov.cn")

    eval_path = record_wrapper_eval(
        worktree=tmp_path,
        args=args,
        branch="agent/feature-20260429-codegen-example-t1",
        log_file=tmp_path / "runtime/codegen/example.log",
        opencode_rc=0,
        gates={"pytest_all": True},
        overall=True,
    )
    eval_path.write_text("# Agent Eval\n\nagent content\n", encoding="utf-8")

    appended_path = record_wrapper_eval(
        worktree=tmp_path,
        args=args,
        branch="agent/feature-20260429-codegen-example-t1",
        log_file=tmp_path / "runtime/codegen/example.log",
        opencode_rc=0,
        gates={"golden": False},
        overall=False,
    )

    assert appended_path == eval_path
    text = appended_path.read_text(encoding="utf-8")
    assert text.startswith("# Agent Eval")
    assert "## Wrapper Gate Result" in text
    assert "| golden | FAIL |" in text
