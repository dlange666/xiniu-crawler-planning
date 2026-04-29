#!/usr/bin/env python3
"""一键 codegen：claim task → worktree → opencode → gates → eval → publish。

用法：
    uv run python scripts/run_codegen.py \\
        --host www.most.gov.cn \\
        --entry-url https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/ \\
        --scope-mode same_origin \\
        --model opencode/minimax-m2.5-free

    uv run python scripts/run_codegen.py \\
        --from-task-db \\
        --task-db runtime/db/dev.db \\
        --model opencode/minimax-m2.5-free

退出码：0 = 全部 gate 通过；1 = 任一 gate 失败。
green 自动提交并推送完整产物；red 只提交并推送 eval 诊断。
失败时 worktree 保留以便人工查证。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from infra.codegen.eval_writer import record_wrapper_eval  # noqa: E402
from infra.codegen.gates import GateRunResult, run_gates  # noqa: E402
from infra.codegen.opencode import invoke_opencode  # noqa: E402
from infra.codegen.paths import slug  # noqa: E402
from infra.codegen.prompt import (  # noqa: E402
    write_feedback_prompt,
    write_per_task_prompt,
    write_task_skeleton,
)
from infra.codegen.publish import commit_and_push_codegen_result  # noqa: E402
from infra.codegen.task_db import (  # noqa: E402
    CodegenDbTask,
    apply_db_task_to_args,
    claim_codegen_task,
    mark_codegen_task_finished,
)
from infra.codegen.worktree import setup_worktree  # noqa: E402

PIPELINE = REPO / "docs/codegen-pipeline.md"
DEFAULT_TASK_DB = REPO / "runtime/db/dev.db"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", help="例：www.most.gov.cn；--from-task-db 模式下自动填充")
    ap.add_argument("--entry-url", help="入口 URL；--from-task-db 模式下自动填充")
    ap.add_argument("--business-context", default="gov_policy")
    ap.add_argument(
        "--scope-mode", default="same_origin",
        choices=["same_origin", "same_etld_plus_one", "url_pattern", "allowlist"],
    )
    ap.add_argument("--scope-url-pattern", default=None)
    ap.add_argument("--model", default="opencode/minimax-m2.5-free",
                    help="opencode 模型 ID，可换 sonnet / opus / 其它")
    ap.add_argument("--from-task-db", action="store_true",
                    help="从 crawl_task/crawl_task_execution 中自动 claim 一个 scheduled 任务")
    ap.add_argument("--task-db", type=Path, default=DEFAULT_TASK_DB,
                    help="--from-task-db 使用的 SQLite DB 路径")
    ap.add_argument(
        "--task-id", type=int, default=None,
        help="--from-task-db 时指定要 claim 的 crawl_task.task_id；默认取下一条 scheduled",
    )
    ap.add_argument("--worker-id", default=f"codegen-runner-{os.getpid()}")
    ap.add_argument("--worktree-base", default=str(REPO.parent),
                    help="worktree 父目录")
    ap.add_argument("--force", action="store_true",
                    help="worktree 已存在时清理重建")
    ap.add_argument("--smoke-task-id", type=int, default=None)
    ap.add_argument("--skip-codegen", action="store_true",
                    help="只跑 gate（agent 产物已就位时调试用）")
    ap.add_argument(
        "--max-red-iterations", type=int, default=3,
        help="wrapper gate red 后自动回喂失败证据的最大次数",
    )
    ap.add_argument(
        "--auto-commit", action=argparse.BooleanOptionalAction, default=True,
        help="green 时自动提交并推送 codegen 产物；red 时只提交并推送 eval 诊断报告",
    )
    return ap


def main() -> int:
    args = build_parser().parse_args()

    claimed_task: CodegenDbTask | None = None
    if args.from_task_db:
        claimed_task = claim_codegen_task(
            args.task_db, task_id=args.task_id, worker_id=args.worker_id,
        )
        if claimed_task is None:
            sys.exit("no scheduled crawl_task found to claim")
        apply_db_task_to_args(args, claimed_task)
    elif not args.host or not args.entry_url:
        build_parser().error("--host and --entry-url are required unless --from-task-db is set")

    if args.smoke_task_id is None:
        args.smoke_task_id = int(time.strftime("%H%M%S"))
    args.codegen_task_id = getattr(args, "codegen_task_id", None)
    args.data_kind = getattr(args, "data_kind", "policy")
    args.max_pages_per_run = getattr(args, "max_pages_per_run", None)
    args.politeness_rps = getattr(args, "politeness_rps", None)
    args.scope_description = getattr(args, "scope_description", None)

    host_slug = slug(args.host)
    task_suffix = f"-t{args.codegen_task_id}" if args.codegen_task_id is not None else ""
    branch = f"agent/feature-{date.today():%Y%m%d}-codegen-{host_slug}{task_suffix}"
    worktree = (
        Path(args.worktree_base) / f"xiniu-crawler-codegen-{host_slug}{task_suffix}"
    ).resolve()
    log_dir = REPO / "runtime/codegen"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = int(time.time())
    log_file = log_dir / f"{host_slug}-{run_stamp}.log"

    print(f"=== codegen for {args.host} ===")
    if claimed_task is not None:
        print(f"  source task      : crawl_task #{claimed_task.task_id} ({args.task_db})")
    print(f"  business_context : {args.business_context}")
    print(f"  data_kind        : {args.data_kind}")
    print(f"  entry_url        : {args.entry_url}")
    print(f"  scope_mode       : {args.scope_mode}")
    if args.scope_url_pattern:
        print(f"  scope_pattern    : {args.scope_url_pattern}")
    print(f"  model            : {args.model}")
    print(f"  worktree         : {worktree}")
    print(f"  branch           : {branch}")
    print(f"  smoke task_id    : {args.smoke_task_id}")
    print(f"  log              : {log_file}")

    if not PIPELINE.exists():
        sys.exit(f"missing codegen pipeline file: {PIPELINE}")

    overall = False
    gates: dict[str, bool] = {}
    gate_details: dict[str, str] = {}
    opencode_rc: int | None = None
    gate_error: str | None = None
    eval_path: Path | None = None
    publish_ok: bool | None = None
    try:
        if not args.skip_codegen:
            setup_worktree(worktree, branch, args.force)
            task_path = write_task_skeleton(worktree, args, branch)
            print(f"[codegen] wrote task JSON skeleton: {task_path}")
            write_per_task_prompt(worktree, args)

        attempts = 1 if args.skip_codegen else max(1, args.max_red_iterations + 1)
        feedback_file: Path | None = None
        for attempt in range(1, attempts + 1):
            if not args.skip_codegen:
                log_file = log_dir / f"{host_slug}-{run_stamp}-attempt{attempt}.log"
                opencode_rc = invoke_opencode(
                    worktree, args.model, log_file, feedback_file=feedback_file,
                )
                print(f"\n[codegen] opencode exit code: {opencode_rc}")
                if opencode_rc != 0:
                    print("opencode 失败；仍继续跑 wrapper gates → ", worktree)

            print(f"\n=== 验收门 attempt {attempt}/{attempts} ===")
            gate_error = None
            try:
                gate_run = run_gates(worktree, args, args.smoke_task_id)
                gates = gate_run.results
                gate_details = gate_run.details
            except Exception as e:  # noqa: BLE001
                gate_error = f"{type(e).__name__}: {e}"
                gates = {"wrapper_exception": False}
                gate_details = {"wrapper_exception": gate_error}
                print(f"[gate] wrapper exception: {gate_error}")
            print("\n=== gate 结果 ===")
            for name, ok in gates.items():
                print(f"  {name:20s}: {'PASS' if ok else 'FAIL'}")

            overall = all(gates.values())
            if overall or args.skip_codegen or attempt >= attempts:
                break
            feedback_file = write_feedback_prompt(
                worktree, args, GateRunResult(gates, gate_details), attempt,
            )
            print(f"[codegen] wrote red feedback prompt: {feedback_file}")

        eval_path = record_wrapper_eval(
            worktree=worktree,
            args=args,
            branch=branch,
            log_file=log_file,
            opencode_rc=opencode_rc,
            gates=gates,
            overall=overall,
            gate_error=gate_error,
            gate_details=gate_details,
        )
        print(f"[eval] wrapper evidence: {eval_path}")
        if args.auto_commit:
            print("\n=== 自动提交 ===")
            publish_ok = commit_and_push_codegen_result(
                worktree=worktree,
                args=args,
                branch=branch,
                eval_path=eval_path,
                overall=overall,
            )
            print(f"[publish] {'PASS' if publish_ok else 'FAIL'}")
    finally:
        if claimed_task is not None:
            mark_codegen_task_finished(
                args.task_db,
                task_id=claimed_task.task_id,
                success=overall and (publish_ok is not False),
                branch=branch,
                worker_id=args.worker_id,
                eval_path=eval_path,
                failed_gates=[name for name, ok in gates.items() if not ok],
            )

    verdict = "green" if overall else "red"
    print(f"\n=== 整体判定: {verdict.upper()} ===")
    print("\n下一步：")
    if overall:
        print(f"  1. 人工 review worktree: {worktree}")
        if args.auto_commit:
            print(f"  2. 分支已自动提交并推送：{branch}")
            print("  3. review 后开 draft PR：")
        else:
            print("  2. 没问题就提交、推送并开 draft PR：")
            print(f"     git -C {worktree} status --short")
            print(f"     git -C {worktree} add <changed files>")
            print(
                f"     git -C {worktree} commit -m "
                f"\"feature({host_slug}): add codegen adapter\""
            )
            print(f"     git -C {worktree} push -u origin {branch}")
        print(
            f"     gh pr create --draft --base main --head {branch} "
            f"--title \"feature({host_slug}): add codegen adapter\""
        )
        print("  4. PR review green 后再 merge；notify-message 暂用 eval 里的草稿。")
    else:
        if args.auto_commit:
            print(f"  1. red eval 已自动提交并推送到分支：{branch}")
        else:
            print("  1. 看失败的 gate（上面 FAIL 行）")
        print(f"  2. 看 codegen 日志：{log_file}")
        print("  3. 看 worktree 里的 eval：")
        print(f"     {worktree}/docs/eval-test/codegen-{host_slug}-*.md")
        print("  4. 修补 / 换 model / 换站点重跑")

    return 0 if overall and publish_ok is not False else 1


if __name__ == "__main__":
    sys.exit(main())
