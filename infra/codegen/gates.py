"""Pipeline §5 验收门：跑全套 gate 并返回确定性结果。"""

from __future__ import annotations

import argparse
import os
import textwrap
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from infra.codegen.golden import validate_golden_artifacts
from infra.codegen.paths import (
    adapter_test_artifact,
    seed_artifact,
    slug,
    source_dir,
    task_artifact_path,
)
from infra.codegen.shell import CommandResult, clip, sh_capture
from infra.codegen.task_json import normalize_task_json


@dataclass(frozen=True)
class GateRunResult:
    results: dict[str, bool]
    details: dict[str, str]


def workflow_artifacts_exist(worktree: Path, args: argparse.Namespace) -> bool:
    host_slug = slug(args.host)
    today = date.today()
    expected = [
        worktree / f"docs/exec-plan/active/plan-{today:%Y%m%d}-codegen-{host_slug}.md",
        worktree / f"docs/task/active/task-codegen-{host_slug}-{today}.json",
        worktree / f"docs/eval-test/codegen-{host_slug}-{today:%Y%m%d}.md",
    ]
    missing = [p.relative_to(worktree) for p in expected if not p.exists()]
    if missing:
        print("[gate] workflow docs missing:")
        for p in missing:
            print(f"  - {p}")
        return False
    return True


def detail_url_pattern_gate(
    worktree: Path,
    args: argparse.Namespace,
    smoke_db: Path,
    smoke_task_id: int,
) -> CommandResult:
    script = textwrap.dedent(f"""\
        import sqlite3
        from infra import adapter_registry

        adapter_registry.discover()
        entry = adapter_registry.get({args.business_context!r}, {args.host!r})
        pattern = entry.detail_url_pattern
        con = sqlite3.connect({str(smoke_db)!r})
        rows = con.execute(
            "SELECT url FROM crawl_raw WHERE task_id=? ORDER BY url",
            ({smoke_task_id},),
        ).fetchall()
        total = len(rows)
        matched = sum(1 for (url,) in rows if pattern.search(url))
        rate = matched / total if total else 0.0
        print(f"detail_url_pattern_match_rate: {{rate:.1%}} ({{matched}}/{{total}})")
        if total:
            misses = [url for (url,) in rows if not pattern.search(url)]
            for url in misses[:5]:
                print(f"miss: {{url}}")
        raise SystemExit(0 if total > 0 and rate >= 0.95 else 1)
        """)
    return sh_capture(["uv", "run", "python", "-c", script], cwd=worktree)


def run_gates(worktree: Path, args: argparse.Namespace, smoke_task_id: int) -> GateRunResult:
    """跑 pipeline §5 全套验收门，返回确定性结果和诊断输出。"""
    res: dict[str, bool] = {}
    details: dict[str, str] = {}
    runtime = worktree / "runtime"
    smoke_db = runtime / "db/dev.db"
    smoke_blob_root = runtime / "raw"
    gate_env = {
        **dict(os.environ),
        "STORAGE_PROFILE": "dev",
        "CRAWLER_DB_PATH": str(smoke_db),
        "CRAWLER_BLOB_ROOT": str(smoke_blob_root),
    }

    def record(name: str, result: CommandResult) -> None:
        res[name] = result.ok
        details[name] = clip(result.output)

    record(
        "pytest_all",
        sh_capture(["uv", "run", "pytest", "tests/", "-q"], cwd=worktree, env=gate_env),
    )
    record(
        "pytest_new",
        sh_capture(
            [
                "uv", "run", "pytest",
                str(adapter_test_artifact(worktree, args).relative_to(worktree)), "-v",
            ],
            cwd=worktree, env=gate_env,
        ),
    )
    record(
        "registry",
        sh_capture(
            ["uv", "run", "python", "-c",
             f"from infra import adapter_registry; "
             f"adapter_registry.discover(); "
             f"print(adapter_registry.get('{args.business_context}', '{args.host}'))"],
            cwd=worktree, env=gate_env,
        ),
    )

    res["workflow_docs"] = workflow_artifacts_exist(worktree, args)
    details["workflow_docs"] = (
        "workflow docs present" if res["workflow_docs"] else "missing workflow docs"
    )

    task_result = normalize_task_json(task_artifact_path(worktree, args))
    res["task_json"] = task_result.ok
    if task_result.ok and task_result.repaired:
        print("[gate] task JSON repaired to canonical JSON")
    elif not task_result.ok:
        print(f"[gate] task JSON invalid: {task_result.error}")
    details["task_json"] = "ok" if task_result.ok else (task_result.error or "invalid")

    golden_ok, golden_detail = validate_golden_artifacts(
        source_dir(worktree, args), slug(args.host)
    )
    res["golden"] = golden_ok
    if not golden_ok:
        print(f"[gate] golden artifacts invalid: {golden_detail}")
    details["golden"] = golden_detail

    if smoke_db.exists():
        smoke_db.unlink()
    for stale in (worktree / "runtime/db").glob("dev.db-*"):
        stale.unlink()
    smoke_cmd = [
        "uv", "run", "python", "scripts/run_crawl_task.py",
        str(seed_artifact(worktree, args).relative_to(worktree)),
        "--max-pages", "30", "--max-depth", "1",
        "--scope-mode", args.scope_mode,
        "--business-context", args.business_context,
        "--task-id", str(smoke_task_id),
    ]
    if getattr(args, "scope_url_pattern", None):
        smoke_cmd.extend(["--scope-url-pattern", args.scope_url_pattern])
    smoke_result = sh_capture(smoke_cmd, cwd=worktree, env=gate_env)
    res["live_smoke"] = smoke_result.ok
    details["live_smoke"] = clip(smoke_result.output)
    if not res["live_smoke"]:
        # 偶发 sqlite I/O 错误：清 WAL/SHM 后重试一次
        print("[gate] live_smoke 失败，1 秒后重试一次")
        time.sleep(1)
        for stale in (worktree / "runtime/db").glob("dev.db*"):
            stale.unlink()
        retry = sh_capture(smoke_cmd, cwd=worktree, env=gate_env)
        res["live_smoke"] = retry.ok
        details["live_smoke"] += "\n\n--- retry ---\n" + clip(retry.output)

    record(
        "audit",
        sh_capture(
            ["uv", "run", "python", "scripts/audit_crawl_quality.py",
             "--task-id", str(smoke_task_id),
             "--db", str(smoke_db)],
            cwd=worktree, env=gate_env,
        ),
    )

    if res["live_smoke"]:
        record(
            "detail_url_pattern",
            detail_url_pattern_gate(worktree, args, smoke_db, smoke_task_id),
        )
    else:
        res["detail_url_pattern"] = False
        details["detail_url_pattern"] = "skipped because live_smoke failed"
    return GateRunResult(res, details)
