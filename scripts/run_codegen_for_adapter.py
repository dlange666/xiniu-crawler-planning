#!/usr/bin/env python3
"""一键 codegen：从参数或 crawl_task 表取任务，产出 adapter + plan + task + eval。

把"claim task → git worktree → plan → task → 调 opencode → gates → eval →
PR handoff"这套流程封装成单脚本。模型由 --model 参数指定，可换 minimax /
sonnet / 其它。

用法：
    uv run python scripts/run_codegen_for_adapter.py \\
        --host www.most.gov.cn \\
        --entry-url https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/ \\
        --scope-mode same_origin \\
        --model opencode/minimax-m2.5-free

    uv run python scripts/run_codegen_for_adapter.py \\
        --from-task-db \\
        --task-db runtime/db/dev.db \\
        --model opencode/minimax-m2.5-free

退出码：0=audit pass，1=任意 gate fail。
失败时 worktree 不会被删，方便人工查证；成功后由人决定合回主分支。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from infra.storage.sqlite_store import SqliteMetadataStore  # noqa: E402

PIPELINE = REPO / "docs/codegen-pipeline.md"
DEFAULT_TASK_DB = REPO / "runtime/db/dev.db"


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


def slug(host: str) -> str:
    """www.most.gov.cn → most"""
    return host.replace("www.", "").split(".")[0].replace("-", "_")


def context_spec_name(business_context: str) -> str:
    """gov_policy -> domain-gov-policy.md."""
    return f"domain-{business_context.replace('_', '-')}.md"


def sh(
    cmd: list[str], *, cwd: Path | None = None,
    check: bool = True, env: dict[str, str] | None = None,
) -> int:
    """执行命令，stdout/stderr 直通终端。"""
    print(f"\n$ {' '.join(cmd)}")
    rc = subprocess.run(cmd, cwd=cwd, env=env).returncode
    if check and rc != 0:
        sys.exit(rc)
    return rc


def sh_ok(
    cmd: list[str], *, cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    return sh(cmd, cwd=cwd, check=False, env=env) == 0


def write_per_task_prompt(worktree: Path, args: argparse.Namespace) -> Path:
    """生成本次的 .codegen-prompt.md，pipeline 之外的目标特化部分。"""
    host_slug = slug(args.host)
    spec_name = context_spec_name(args.business_context)
    today = date.today()
    task_id = getattr(args, "codegen_task_id", None)
    data_kind = getattr(args, "data_kind", "policy")
    scope_description = getattr(args, "scope_description", None)
    task_line = f"| crawl_task.task_id | `{task_id}` |\n" if task_id is not None else ""
    scope_line = (
        f"| scope_description | `{scope_description}` |\n"
        if scope_description else ""
    )
    prompt = textwrap.dedent(f"""\
        # 任务：为 {args.host} 实现采集适配器

        > **前置阅读**：你已加载 `docs/codegen-pipeline.md`。**严格按它执行**——
        > git-worktree / plan / task / gates / eval / PR handoff / notify-message
        > 的顺序和允许写入范围都在 pipeline 里。

        ## 目标

        | 项 | 值 |
        |---|---|
        | business_context | `{args.business_context}` |
        | data_kind | `{data_kind}` |
        | host | `{args.host}` |
        | entry URL | `{args.entry_url}` |
        | scope_mode | `{args.scope_mode}` |
        {task_line}{scope_line}\
        | render_mode | `direct`（确认是 SSR 后再写；JS 渲染站本期不接） |

        ## 必须交付

        按 pipeline §4 工作流：

        1. 写 plan：`docs/exec-plan/active/plan-{today:%Y%m%d}-codegen-{host_slug}.md`
        2. 写 task：`docs/task/active/task-codegen-{host_slug}-{today}.json`
        3. 实现：
           - `domains/{args.business_context}/adapters/{host_slug}.py`
           - `domains/{args.business_context}/seeds/{host_slug}.yaml`
             （**必须**含 `scope_mode: {args.scope_mode}`）
           - `domains/{args.business_context}/golden/{host_slug}/...`
           - `tests/{args.business_context}/test_adapter_{host_slug}.py`
        4. 跑 pipeline §4.5 的验收门，**包括 live smoke + audit 脚本**
        5. 写 eval：`docs/eval-test/codegen-{host_slug}-{today:%Y%m%d}.md`，判定来自 audit 退出码
        6. eval 最后一节写 PR handoff 与 notify-message 草稿

        ## 你需要自己探的事

        - 翻页：实际 fetch 一次列表页，看是否有 `index_N.htm` / `?page=N`
          / "下一页"按钮，按 pipeline §3 选 helper
        - 详情 URL 模式：从列表 HTML 里抽 5+ 链接，归纳 detail_url_pattern 正则
        - 跨子域：如详情链接散布到 `*.{args.host.replace("www.", "")}` 的子站，
          seed 必须设 `scope_mode: same_etld_plus_one`，且 CLI 也要显式同步（已知陷阱）
        - 详情字段：参考 `docs/prod-spec/{spec_name}` 的字段表
          （title / body / 发文字号 / 发文机关 / 成文日期 / 发布日期
          / attachments / interpret_links）

        ## 给我的最终回报

        eval 写完后告诉我：

        1. audit 输出（粘贴 audit_crawl_quality.py 的 stdout）
        2. 验收判定（green / red / partial）+ 失败的 gate（如 red）
        3. 子域分布与 cohort 质量（audit 已输出，简述）
        4. 已知 todo（哪些字段 / cohort 没覆盖到）
    """)
    f = worktree / ".codegen-prompt.md"
    f.write_text(prompt)
    return f


def setup_worktree(worktree: Path, branch: str, force: bool) -> None:
    """幂等创建 worktree。--force 触发硬重置：rm -rf + prune + 删分支。

    硬重置必要性：opencode 偶尔异常退出会留下 worktree 半完成状态，
    `git worktree remove --force` 不一定能清理干净。
    """
    if worktree.exists() or branch_exists(branch):
        if not force:
            sys.exit(f"worktree/branch 已存在：{worktree} / {branch}（加 --force 硬重置）")
        print(f"硬清理 worktree + branch：{worktree} / {branch}")
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
        sh(["git", "worktree", "prune"], check=False)
        if branch_exists(branch):
            sh(["git", "branch", "-D", branch], check=False)
    sh(["git", "worktree", "add", "-b", branch, str(worktree), "HEAD"])


def branch_exists(branch: str) -> bool:
    rc = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
    ).returncode
    return rc == 0


def claim_codegen_task(
    db_path: Path,
    *,
    task_id: int | None,
    worker_id: str,
) -> CodegenDbTask | None:
    """Claim one scheduled crawl_task row for local codegen.

    SQLite lacks SKIP LOCKED, so the dev runner uses BEGIN IMMEDIATE to serialize
    claims. The full external TaskSource can later map this behavior to its own
    lock primitive.
    """
    schema = SqliteMetadataStore(db_path)
    schema.init_schema()
    schema.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        if task_id is None:
            row = conn.execute(
                """SELECT
                    t.task_id, t.business_context, t.site_url, t.host, t.data_kind,
                    t.scope_mode, t.scope_url_pattern, t.max_pages_per_run,
                    t.politeness_rps, t.scope_description
                FROM crawl_task t
                LEFT JOIN crawl_task_execution e ON e.task_id = t.task_id
                WHERE COALESCE(e.status, 'scheduled') = 'scheduled'
                  AND (
                    e.next_run_at IS NULL
                    OR e.next_run_at <= strftime('%Y-%m-%dT%H:%M:%fZ','now')
                  )
                ORDER BY t.priority ASC, t.created_at ASC, t.task_id ASC
                LIMIT 1"""
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT
                    t.task_id, t.business_context, t.site_url, t.host, t.data_kind,
                    t.scope_mode, t.scope_url_pattern, t.max_pages_per_run,
                    t.politeness_rps, t.scope_description
                FROM crawl_task t
                LEFT JOIN crawl_task_execution e ON e.task_id = t.task_id
                WHERE t.task_id = ?
                  AND COALESCE(e.status, 'scheduled') = 'scheduled'""",
                (task_id,),
            ).fetchone()

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
) -> None:
    status = "completed" if success else "failed"
    run_status = "green" if success else "red"
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
                    heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE task_id=?""",
                (status, branch, run_status, 1 if success else 0, worker_id, task_id),
            )
    finally:
        conn.close()


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


def golden_artifacts_exist(worktree: Path, args: argparse.Namespace) -> bool:
    golden_dir = (
        worktree / "domains" / args.business_context / "golden" / slug(args.host)
    )
    html_count = len(list(golden_dir.glob("*.html")))
    json_count = len(list(golden_dir.glob("*.golden.json")))
    if html_count < 5 or json_count < 5:
        print(
            "[gate] golden artifacts insufficient: "
            f"html={html_count}, golden_json={json_count}, required>=5 each"
        )
        return False
    return True


def invoke_opencode(worktree: Path, model: str, log_file: Path) -> int:
    """用 opencode 原生 file attachment 加载 pipeline + per-task prompt。"""
    print(f"\n[codegen] invoking {model} ... 输出 → {log_file}")
    with open(log_file, "w") as logf:
        proc = subprocess.Popen(
            [
                "opencode", "run",
                "Execute the attached codegen pipeline for this single-host task.",
                "-m", model,
                "-f", "docs/codegen-pipeline.md",
                "-f", ".codegen-prompt.md",
            ],
            cwd=worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            logf.write(line)
            logf.flush()
            # 简化输出到终端（去 ANSI）
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).rstrip()
            if clean:
                print(f"  [agent] {clean[:140]}")
        return proc.wait()


def run_gates(worktree: Path, args: argparse.Namespace, smoke_task_id: int) -> dict:
    """跑 pipeline §4.5 全套验收门，返回 {gate: pass|fail}。"""
    res: dict[str, bool] = {}
    runtime = worktree / "runtime"
    smoke_db = runtime / "db/dev.db"
    smoke_blob_root = runtime / "raw"
    gate_env = {
        **dict(os.environ),
        "STORAGE_PROFILE": "dev",
        "CRAWLER_DB_PATH": str(smoke_db),
        "CRAWLER_BLOB_ROOT": str(smoke_blob_root),
    }
    res["pytest_all"] = sh_ok(
        ["uv", "run", "pytest", "tests/", "-q"], cwd=worktree, env=gate_env)
    res["pytest_new"] = sh_ok(
        ["uv", "run", "pytest",
         f"tests/{args.business_context}/test_adapter_{slug(args.host)}.py", "-v"],
        cwd=worktree, env=gate_env)
    res["registry"] = sh_ok(
        ["uv", "run", "python", "-c",
         f"from infra import adapter_registry; "
         f"adapter_registry.discover(); "
         f"print(adapter_registry.get('{args.business_context}', '{args.host}'))"],
        cwd=worktree, env=gate_env)
    res["workflow_docs"] = workflow_artifacts_exist(worktree, args)
    res["golden"] = golden_artifacts_exist(worktree, args)
    if smoke_db.exists():
        smoke_db.unlink()
    # 清掉 WAL/SHM 文件，规避 sqlite 偶发 disk I/O error
    for stale in (worktree / "runtime/db").glob("dev.db-*"):
        stale.unlink()
    smoke_cmd = [
        "uv", "run", "python", "scripts/run_crawl_task.py",
        f"domains/{args.business_context}/seeds/{slug(args.host)}.yaml",
        "--max-pages", "30", "--max-depth", "1",
        "--scope-mode", args.scope_mode,
        "--business-context", args.business_context,
        "--task-id", str(smoke_task_id),
    ]
    if getattr(args, "scope_url_pattern", None):
        smoke_cmd.extend(["--scope-url-pattern", args.scope_url_pattern])
    res["live_smoke"] = sh_ok(smoke_cmd, cwd=worktree, env=gate_env)
    if not res["live_smoke"]:
        # 偶发 sqlite I/O 错误重试一次
        print("[gate] live_smoke 失败，1 秒后重试一次")
        time.sleep(1)
        for stale in (worktree / "runtime/db").glob("dev.db*"):
            stale.unlink()
        res["live_smoke"] = sh_ok(smoke_cmd, cwd=worktree, env=gate_env)
    res["audit"] = sh_ok(
        ["uv", "run", "python", "scripts/audit_crawl_quality.py",
         "--task-id", str(smoke_task_id),
         "--db", str(smoke_db)],
        cwd=worktree, env=gate_env)
    return res


def main() -> int:
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
    args = ap.parse_args()

    claimed_task: CodegenDbTask | None = None
    if args.from_task_db:
        claimed_task = claim_codegen_task(
            args.task_db, task_id=args.task_id, worker_id=args.worker_id,
        )
        if claimed_task is None:
            sys.exit("no scheduled crawl_task found to claim")
        apply_db_task_to_args(args, claimed_task)
    elif not args.host or not args.entry_url:
        ap.error("--host and --entry-url are required unless --from-task-db is set")

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
    log_file = REPO / f"runtime/codegen/{host_slug}-{int(time.time())}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

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
    try:
        if not args.skip_codegen:
            setup_worktree(worktree, branch, args.force)
            write_per_task_prompt(worktree, args)
            rc = invoke_opencode(worktree, args.model, log_file)
            print(f"\n[codegen] opencode exit code: {rc}")
            if rc != 0:
                print("opencode 失败；worktree 留存供人工查 → ", worktree)

        # 跑验收门，无论 opencode 退出码如何（agent 退出码不可信）
        print("\n=== 验收门 ===")
        gates = run_gates(worktree, args, args.smoke_task_id)
        print("\n=== gate 结果 ===")
        for name, ok in gates.items():
            print(f"  {name:14s}: {'PASS' if ok else 'FAIL'}")

        overall = all(gates.values())
    finally:
        if claimed_task is not None:
            mark_codegen_task_finished(
                args.task_db,
                task_id=claimed_task.task_id,
                success=overall,
                branch=branch,
                worker_id=args.worker_id,
            )

    verdict = "green" if overall else "red"
    print(f"\n=== 整体判定: {verdict.upper()} ===")
    print("\n下一步：")
    if overall:
        print(f"  1. 人工 review worktree: {worktree}")
        print("  2. 没问题就提交、推送并开 draft PR：")
        print(f"     git -C {worktree} status --short")
        print(f"     git -C {worktree} add <changed files>")
        print(f"     git -C {worktree} commit -m \"feature({host_slug}): add codegen adapter\"")
        print(f"     git -C {worktree} push -u origin {branch}")
        print(
            f"     gh pr create --draft --base main --head {branch} "
            f"--title \"feature({host_slug}): add codegen adapter\""
        )
        print("  3. PR review green 后再 merge；notify-message 暂用 eval 里的草稿。")
    else:
        print("  1. 看失败的 gate（上面 FAIL 行）")
        print(f"  2. 看 codegen 日志：{log_file}")
        print("  3. 看 worktree 里 agent 写的 eval：")
        print(f"     {worktree}/docs/eval-test/codegen-{host_slug}-*.md")
        print("  4. 修补 / 换 model / 换站点重跑")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
