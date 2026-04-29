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
import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple

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


class JsonValidationResult(NamedTuple):
    ok: bool
    repaired: bool
    error: str | None = None


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    output: str


@dataclass(frozen=True)
class GateRunResult:
    results: dict[str, bool]
    details: dict[str, str]


def slug(host: str) -> str:
    """Return the adapter slug for a host.

    Adapter file names must identify the owning source, not a generic delivery
    channel such as www/wap/search. Examples:
    - www.most.gov.cn -> most
    - wap.miit.gov.cn -> miit
    - search.sh.gov.cn -> sh_search
    """
    labels = [label for label in host.lower().split(".") if label]
    if not labels:
        return "unknown"

    service_prefixes = {"www", "wap", "m", "mobile"}
    searchable_prefixes = {"search", "sousuo"}
    suffixes = {
        ("gov", "cn"),
        ("com", "cn"),
        ("org", "cn"),
        ("net", "cn"),
        ("edu", "cn"),
        ("ac", "cn"),
    }
    removed_suffix: tuple[str, ...] = ()
    if len(labels) >= 2 and tuple(labels[-2:]) in suffixes:
        removed_suffix = tuple(labels[-2:])
        labels = labels[:-2]
    elif len(labels) >= 1:
        removed_suffix = (labels[-1],)
        labels = labels[:-1]

    dropped: list[str] = []
    while labels and labels[0] in service_prefixes | searchable_prefixes:
        dropped.append(labels.pop(0))

    if not labels and removed_suffix == ("gov", "cn"):
        labels = ["gov"]
    elif not labels:
        labels = [label for label in host.lower().split(".") if label][:1]

    source = labels[0]
    if any(prefix in searchable_prefixes for prefix in dropped):
        source = f"{source}_search"
    return re.sub(r"[^a-z0-9]+", "_", source).strip("_") or "unknown"


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


def sh_capture(
    cmd: list[str], *, cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    return CommandResult(proc.returncode == 0, proc.stdout)


def _clip(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def source_dir(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / "domains" / args.business_context / slug(args.host)


def adapter_artifact(worktree: Path, args: argparse.Namespace) -> Path:
    host_slug = slug(args.host)
    return source_dir(worktree, args) / f"{host_slug}_adapter.py"


def seed_artifact(worktree: Path, args: argparse.Namespace) -> Path:
    host_slug = slug(args.host)
    return source_dir(worktree, args) / f"{host_slug}_seed.yaml"


def adapter_test_artifact(worktree: Path, args: argparse.Namespace) -> Path:
    host_slug = slug(args.host)
    return worktree / "tests" / args.business_context / f"test_{host_slug}_adapter.py"


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

        按 pipeline §4-§6 工作流：

        1. 写 plan：`docs/exec-plan/active/plan-{today:%Y%m%d}-codegen-{host_slug}.md`
        2. 更新 task：wrapper 已预先生成合法 JSON 骨架
           `docs/task/active/task-codegen-{host_slug}-{today}.json`。只允许编辑 JSON
           字段值，不要输出 markdown fence、注释、尾逗号或任何 JSON 外文本；
           每次编辑后必须执行 `uv run python -m json.tool <task-json>`。
        3. 实现：
           - `domains/{args.business_context}/{host_slug}/{host_slug}_adapter.py`
           - `domains/{args.business_context}/{host_slug}/{host_slug}_seed.yaml`
             （**必须**含 `scope_mode: {args.scope_mode}`）
           - `domains/{args.business_context}/{host_slug}/{host_slug}_golden_*.html`
           - `domains/{args.business_context}/{host_slug}/{host_slug}_golden_*.golden.json`
           - `tests/{args.business_context}/test_{host_slug}_adapter.py`
        4. 跑 pipeline §5 的验收门，**包括 live smoke + audit 脚本**
        5. 写 eval：`docs/eval-test/codegen-{host_slug}-{today:%Y%m%d}.md`，判定来自 audit 退出码
        6. eval 最后一节写 PR handoff 与 notify-message 草稿

        ## 强制收口协议

        你不能在完成代码后直接结束。每次实现或修复后，必须按顺序执行：

        ```bash
        uv run pytest tests/{args.business_context}/test_{host_slug}_adapter.py -q
        uv run pytest tests/ -q
        uv run python -c "from infra import adapter_registry; adapter_registry.discover(); \
print(adapter_registry.get('{args.business_context}', '{args.host}'))"
        uv run python -m json.tool docs/task/active/task-codegen-{host_slug}-{today}.json
        uv run python - <<'PY'
        from scripts.run_codegen_for_adapter import golden_artifacts_exist
        import argparse
        from pathlib import Path
        args = argparse.Namespace(host='{args.host}', business_context='{args.business_context}')
        raise SystemExit(0 if golden_artifacts_exist(Path('.'), args) else 1)
        PY
        rm -f runtime/db/dev.db runtime/db/dev.db-wal runtime/db/dev.db-shm
        uv run python scripts/run_crawl_task.py \
domains/{args.business_context}/{host_slug}/{host_slug}_seed.yaml \
--max-pages 30 --max-depth 1 --scope-mode {args.scope_mode} \
--business-context {args.business_context} --task-id {args.smoke_task_id}
        uv run python scripts/audit_crawl_quality.py \
--task-id {args.smoke_task_id} --db runtime/db/dev.db \
--thresholds title_rate=0.95,body_100_rate=0.95,metadata_rate=0.30
        ```

        最终判定只能来自上述 gates：

        - 全部 PASS：eval 写 `green`，task 状态写 `verifying`（PR 创建前不要写 `completed`）
        - 任一 FAIL：eval 写 `red` 或 `partial`，task 状态写 `failed`

        禁止只凭单测 / registry 通过写 green；禁止在 live smoke / audit 未跑时写 green。
        禁止把旧 `runtime/db/dev.db` checkpoint 造成的 0 records 当作源站失败。
        禁止把可通过静态 JSON / CDN / API / feed / SSR 采集的 JS shell 直接写成
        `render_required`。

        ## 解析质量硬规则

        - `ParseDetailResult.source_metadata` 必须写成 `SourceMetadata(raw={{...}})`；
          测试读取必须使用 `result.source_metadata.raw`，不得把 `source_metadata`
          当作普通 dict。
        - `body_text` 不得包含 `var `、`function`、`document.`、`window.`、
          `<script`、`</script`、`$(...)` 等脚本噪声；如正文来自 JS 模板字面量，
          只能抽取正文变量自身，不能从第一个反引号截到最后一个反引号。
        - `detail_links` 必须属于本任务业务 scope。audit 出现 short body sample
          或低质量 URL 时，先判断该 URL 是否是导航、搜索、社媒、移动入口、
          站点说明、栏目页等非政策详情；非业务详情必须在 `parse_list` 或
          `ADAPTER_META.detail_url_pattern` 中过滤，禁止通过降低 gate 通过。
        - `next_pages` 要按自然页码排序，不能出现 `1, 10, 11, 2` 这类字典序。

        ## Golden 覆盖硬规则

        golden 不是只凑数量。必须使用一一配对命名：

        - `{host_slug}_golden_list_1.html` +
          `{host_slug}_golden_list_1.golden.json`
        - `{host_slug}_golden_detail_1.html` +
          `{host_slug}_golden_detail_1.golden.json`（至少 3 个 detail）
        - 若存在分页信号，至少再提供 `{host_slug}_golden_list_2.html` +
          `{host_slug}_golden_list_2.golden.json`

        每个 `.golden.json` 必须由当前 adapter 输出重新生成，并通过
        `uv run python -m json.tool`。聚合型 JSON 不能替代 HTML 同名配对。

        ## red 前必须排查

        如果 live smoke 或 audit 失败，不能立即结束。必须先做并在 eval 记录：

        1. 删除 `runtime/db/dev.db*` 后重跑 live smoke
        2. 单独 curl seed URL，确认 HTTP 状态、content-type 和响应体
        3. 单独调用 `parse_list(seed_response, seed_url)`，确认 `detail_links > 0`
        4. 单独 curl 一个 detail URL，确认 `parse_detail` 抽出 title / body / metadata
        5. 逐条分析 audit short body samples / script_noise / detail_url_pattern
           失败样本，判断是正文抽取污染还是非业务链接误入
        6. parser 单独可用但 runner 无数据时，检查 seed URL、scope、robots、
           runtime checkpoint、`ADAPTER_META.list_url_pattern`
        7. 只有这些检查完成后，才允许写 red

        ## 你需要自己探的事

        - 翻页：实际 fetch 一次列表页，看是否有 `index_N.htm` / `?page=N`
          / "下一页"按钮 / `createPageHTML` / `data-page` / 公开 JS page config，
          按 pipeline §3 先选 `infra/crawl/pagination_helpers.py` helper
        - 如果 infra helper 返回空，但 HTML/JS 中存在明确、稳定、可静态解析的
          分页/API/字段信号，不能直接放弃或写 red。你必须在
          `{host_slug}_adapter.py` 内实现 host-bounded fallback（纯函数、无联网、
          不改 infra），并用 golden/test 覆盖；eval 记录 helper 未覆盖、fallback
          规则，以及是否建议另开 infra 任务提升。**本 codegen 任务禁止修改
          `infra/`；infra 能力由单独 infra 任务补。**
        - 若存在分页信号，`tests/{args.business_context}/test_{host_slug}_adapter.py`
          必须断言 `parse_list(...).next_pages` 至少包含 1 个预期分页 URL；golden
          JSON 也要记录对应 `next_pages`
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


def task_artifact_path(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / f"docs/task/active/task-codegen-{slug(args.host)}-{date.today()}.json"


def write_task_skeleton(worktree: Path, args: argparse.Namespace, branch: str) -> Path:
    """Pre-create the task JSON as canonical JSON before handing control to agent.

    The coding agent should update this file instead of inventing the structure
    from scratch. That removes the most common failure mode: markdown or prose
    wrapped around a JSON-looking object.
    """
    today = date.today()
    host_slug = slug(args.host)
    task_path = task_artifact_path(worktree, args)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    plan_id = f"plan-{today:%Y%m%d}-codegen-{host_slug}"
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "file_kind": "pr-task-file",
        "description": f"codegen-{host_slug}: 为 {args.host} 生成采集适配器。",
        "pr_name": f"codegen-{host_slug}",
        "branch": branch,
        "date": today.isoformat(),
        "status_enum": ["pending", "in_progress", "verifying", "completed", "failed"],
        "tasks": [
            {
                "id": f"T-{today:%Y%m%d}-701",
                "title": f"[codegen/{host_slug}] 生成并验收采集适配器",
                "status": "in_progress",
                "plan_id": plan_id,
                "spec_ref": "codegen-output-contract.md §3.1；docs/codegen-pipeline.md §4",
                "dependency": [],
                "assignee": "generator",
                "last_updated": now,
                "notes": (
                    "wrapper 预生成 JSON 骨架；agent 更新时必须保持标准 JSON，"
                    "wrapper gates 会校验并在常见包裹文本场景下自动规范化。"
                ),
            }
        ],
    }
    task_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return task_path


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
                    str(eval_path) if eval_path else None,
                    0 if success else 1,
                    task_id,
                ),
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


def eval_artifact_path(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / f"docs/eval-test/codegen-{slug(args.host)}-{date.today():%Y%m%d}.md"


def _extract_json_objects(text: str) -> list[str]:
    """Return balanced JSON-looking objects from text, respecting strings."""
    objects: list[str] = []
    starts = [match.start() for match in re.finditer(r"\{", text)]
    for start in starts:
        depth = 0
        in_string = False
        escaped = False
        for idx, char in enumerate(text[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    objects.append(text[start:idx + 1])
                    break
    return objects


def _validate_pr_task_file(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"]

    required = {
        "schema_version",
        "file_kind",
        "description",
        "pr_name",
        "branch",
        "date",
        "status_enum",
        "tasks",
    }
    for key in sorted(required - set(data)):
        errors.append(f"missing top-level key: {key}")

    if data.get("file_kind") != "pr-task-file":
        errors.append("file_kind must be pr-task-file")
    if not isinstance(data.get("status_enum"), list):
        errors.append("status_enum must be a list")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty list")
        return errors

    task_required = {
        "id",
        "title",
        "status",
        "plan_id",
        "dependency",
        "assignee",
        "last_updated",
        "notes",
    }
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        for key in sorted(task_required - set(task)):
            errors.append(f"tasks[{index}] missing key: {key}")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not re.fullmatch(r"T-\d{8}-\d{3}", task_id):
            errors.append(f"tasks[{index}].id must match T-YYYYMMDD-NNN")
        if task.get("status") not in data.get("status_enum", []):
            errors.append(f"tasks[{index}].status is not in status_enum")
        if not isinstance(task.get("dependency", []), list):
            errors.append(f"tasks[{index}].dependency must be a list")
    return errors


def normalize_task_json(path: Path) -> JsonValidationResult:
    """Validate task JSON and canonicalize common non-standard model output.

    The repair is deliberately narrow: it only extracts a balanced JSON object
    from wrappers such as markdown fences or explanatory prose. It does not
    guess missing commas or comments, because that can silently alter meaning.
    """
    if not path.exists():
        return JsonValidationResult(False, False, "task JSON missing")

    raw = path.read_text(encoding="utf-8")
    candidates = [(raw, False)]
    for extracted in _extract_json_objects(raw):
        if extracted == raw.strip():
            continue
        candidates.append((extracted, True))

    last_error: str | None = None
    for candidate, repaired in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = f"JSONDecodeError: {exc.msg} at line {exc.lineno} column {exc.colno}"
            continue
        schema_errors = _validate_pr_task_file(data)
        if schema_errors:
            return JsonValidationResult(False, repaired, "; ".join(schema_errors))
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return JsonValidationResult(True, repaired, None)

    return JsonValidationResult(False, False, last_error or "no JSON object found")


def codegen_task_json_valid(worktree: Path, args: argparse.Namespace) -> bool:
    result = normalize_task_json(task_artifact_path(worktree, args))
    if result.ok:
        if result.repaired:
            print("[gate] task JSON repaired to canonical JSON")
        return True
    print(f"[gate] task JSON invalid: {result.error}")
    return False


def golden_artifacts_exist(worktree: Path, args: argparse.Namespace) -> bool:
    artifacts_dir = source_dir(worktree, args)
    ok, message = validate_golden_artifacts(artifacts_dir, slug(args.host))
    if not ok:
        print(f"[gate] golden artifacts invalid: {message}")
        return False
    return True


def _json_contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_json_contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_json_contains_key(v, key) for v in value)
    return False


def _json_has_nonempty_next_pages(value: Any) -> bool:
    if isinstance(value, dict):
        next_pages = value.get("next_pages")
        if isinstance(next_pages, list) and len(next_pages) > 0:
            return True
        return any(_json_has_nonempty_next_pages(v) for v in value.values())
    if isinstance(value, list):
        return any(_json_has_nonempty_next_pages(v) for v in value)
    return False


def validate_golden_artifacts(artifacts_dir: Path, host_slug: str) -> tuple[bool, str]:
    """Validate coverage-oriented golden files instead of plain file counts."""
    html_files = sorted(artifacts_dir.glob(f"{host_slug}_golden_*.html"))
    json_files = sorted(artifacts_dir.glob(f"{host_slug}_golden_*.golden.json"))
    html_by_stem = {p.with_suffix("").name: p for p in html_files}
    json_by_stem = {p.name.removesuffix(".golden.json"): p for p in json_files}
    paired_stems = sorted(set(html_by_stem) & set(json_by_stem))
    missing_json = sorted(set(html_by_stem) - set(json_by_stem))
    missing_html = sorted(set(json_by_stem) - set(html_by_stem))
    if missing_json:
        return False, f"missing paired golden JSON for: {', '.join(missing_json[:5])}"
    if missing_html:
        return False, f"missing paired golden HTML for: {', '.join(missing_html[:5])}"

    list_pairs = 0
    detail_pairs = 0
    pagination_pairs = 0
    pagination_signal = False
    invalid_json: list[str] = []
    for stem in paired_stems:
        json_path = json_by_stem[stem]
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            invalid_json.append(f"{json_path.name}: {exc.msg}")
            continue
        if "_golden_list_" in stem or stem.endswith("_golden_list"):
            list_pairs += 1
        if "_golden_detail_" in stem or stem.endswith("_golden_detail"):
            detail_pairs += 1
        if re.search(r"_golden_list_(?:[2-9]|\d{2,})$", stem) or "pagination" in stem:
            pagination_pairs += 1
        if _json_contains_key(payload, "parse_list") and _json_has_nonempty_next_pages(payload):
            pagination_signal = True

    if invalid_json:
        return False, "; ".join(invalid_json[:3])
    if len(paired_stems) < 4:
        return False, f"paired golden count={len(paired_stems)}, required>=4"
    if list_pairs < 1:
        return False, "required >=1 paired list golden"
    if detail_pairs < 3:
        return False, f"paired detail golden count={detail_pairs}, required>=3"
    if pagination_signal and pagination_pairs < 1:
        return False, "pagination signal found, required >=1 paired pagination/list_2 golden"
    return True, (
        f"paired={len(paired_stems)}, list={list_pairs}, detail={detail_pairs}, "
        f"pagination={pagination_pairs}"
    )


def invoke_opencode(
    worktree: Path,
    model: str,
    log_file: Path,
    *,
    feedback_file: Path | None = None,
) -> int:
    """用 opencode 原生 file attachment 加载 pipeline + per-task prompt。"""
    print(f"\n[codegen] invoking {model} ... 输出 → {log_file}")
    cmd = [
        "opencode", "run",
        "Execute the attached codegen pipeline for this single-host task.",
        "-m", model,
        "-f", "docs/codegen-pipeline.md",
        "-f", ".codegen-prompt.md",
    ]
    if feedback_file is not None:
        cmd[2] = "Continue the existing codegen task and fix the wrapper red gates."
        cmd.extend(["-f", str(feedback_file.relative_to(worktree))])
    with open(log_file, "w") as logf:
        proc = subprocess.Popen(
            cmd,
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
    cmd_result = sh_capture(
        ["uv", "run", "pytest", "tests/", "-q"], cwd=worktree, env=gate_env)
    res["pytest_all"] = cmd_result.ok
    details["pytest_all"] = _clip(cmd_result.output)
    cmd_result = sh_capture(
        [
            "uv", "run", "pytest",
            str(adapter_test_artifact(worktree, args).relative_to(worktree)), "-v",
        ],
        cwd=worktree, env=gate_env)
    res["pytest_new"] = cmd_result.ok
    details["pytest_new"] = _clip(cmd_result.output)
    cmd_result = sh_capture(
        ["uv", "run", "python", "-c",
         f"from infra import adapter_registry; "
         f"adapter_registry.discover(); "
         f"print(adapter_registry.get('{args.business_context}', '{args.host}'))"],
        cwd=worktree, env=gate_env)
    res["registry"] = cmd_result.ok
    details["registry"] = _clip(cmd_result.output)
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
    # 清掉 WAL/SHM 文件，规避 sqlite 偶发 disk I/O error
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
    cmd_result = sh_capture(smoke_cmd, cwd=worktree, env=gate_env)
    res["live_smoke"] = cmd_result.ok
    details["live_smoke"] = _clip(cmd_result.output)
    if not res["live_smoke"]:
        # 偶发 sqlite I/O 错误重试一次
        print("[gate] live_smoke 失败，1 秒后重试一次")
        time.sleep(1)
        for stale in (worktree / "runtime/db").glob("dev.db*"):
            stale.unlink()
        retry_result = sh_capture(smoke_cmd, cwd=worktree, env=gate_env)
        res["live_smoke"] = retry_result.ok
        details["live_smoke"] += "\n\n--- retry ---\n" + _clip(retry_result.output)
    cmd_result = sh_capture(
        ["uv", "run", "python", "scripts/audit_crawl_quality.py",
         "--task-id", str(smoke_task_id),
         "--db", str(smoke_db)],
        cwd=worktree, env=gate_env)
    res["audit"] = cmd_result.ok
    details["audit"] = _clip(cmd_result.output)
    if res["live_smoke"]:
        cmd_result = detail_url_pattern_gate(worktree, args, smoke_db, smoke_task_id)
        res["detail_url_pattern"] = cmd_result.ok
        details["detail_url_pattern"] = _clip(cmd_result.output)
    else:
        res["detail_url_pattern"] = False
        details["detail_url_pattern"] = "skipped because live_smoke failed"
    return GateRunResult(res, details)


def write_feedback_prompt(
    worktree: Path,
    args: argparse.Namespace,
    gate_run: GateRunResult,
    attempt: int,
) -> Path:
    failed = [name for name, ok in gate_run.results.items() if not ok]
    sections: list[str] = []
    for gate in failed:
        output = gate_run.details.get(gate, "")
        sections.append(f"### {gate}\n\n```text\n{_clip(output, 6000)}\n```")
    if not sections:
        sections.append(
            "No failed gate details were captured; rerun full gates and inspect output."
        )
    failed_output = "\n\n".join(sections)
    path = worktree / ".codegen-feedback.md"
    path.write_text(
        textwrap.dedent(f"""\
        # Wrapper red feedback attempt {attempt}

        The wrapper gates are authoritative. Do not mark eval green until every
        gate below passes. Fix the current worktree in place; do not restart the
        task, do not lower thresholds, and do not modify `infra/`.

        Failed gates: {", ".join(failed) if failed else "none"}

        Required triage:

        1. Read the failing gate output below before editing.
        2. If audit shows short body samples, decide whether each URL is outside
           business scope. Filter non-policy/navigation/search/social/mobile
           links in `parse_list` or tighten `ADAPTER_META.detail_url_pattern`.
        3. If audit shows script noise, fix `parse_detail` so `body_text` excludes
           JS/CSS/nav text. Do not satisfy length gates with polluted text.
        4. If pytest fails around metadata, remember `source_metadata` is
           `SourceMetadata(raw={{...}})` and tests must read `.raw`.
        5. Regenerate paired golden JSON from the current adapter after parser
           fixes. Golden files must be HTML/JSON one-to-one pairs.
        6. Rerun the full closure gates from `.codegen-prompt.md`.

        ## Failed Gate Output

        {failed_output}
        """),
        encoding="utf-8",
    )
    return path


def record_wrapper_eval(
    *,
    worktree: Path,
    args: argparse.Namespace,
    branch: str,
    log_file: Path,
    opencode_rc: int | None,
    gates: dict[str, bool],
    overall: bool,
    gate_error: str | None = None,
    gate_details: dict[str, str] | None = None,
) -> Path:
    """Ensure wrapper-level green/red evidence is written into eval-test.

    opencode is an untrusted worker: it may exit non-zero before writing eval,
    or it may self-report partial while wrapper gates are red. The wrapper owns
    the final gate record and must leave durable evidence in docs/eval-test.
    """
    eval_path = eval_artifact_path(worktree, args)
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    verdict = "green" if overall else "red"
    failed = [name for name, ok in gates.items() if not ok]
    if gate_error:
        failed.append("wrapper_exception")
    gate_rows = "\n".join(
        f"| {name} | {'PASS' if ok else 'FAIL'} |" for name, ok in gates.items()
    )
    if not gate_rows:
        gate_rows = "| gate_not_started | FAIL |"
    failed_text = ", ".join(failed) if failed else "none"
    opencode_text = "not_run" if opencode_rc is None else str(opencode_rc)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    relative_log = log_file
    with contextlib.suppress(ValueError):
        relative_log = log_file.relative_to(REPO)

    wrapper_section = textwrap.dedent(f"""\

        ## Wrapper Gate Result

        > **作者**：codegen wrapper
        > **时间**：{timestamp}
        > **最终判定**：`{verdict}`

        | Gate | Result |
        |---|---|
        {gate_rows}

        | 项 | 值 |
        |---|---|
        | host | `{args.host}` |
        | branch | `{branch}` |
        | opencode_exit_code | `{opencode_text}` |
        | failed_gates | `{failed_text}` |
        | codegen_log | `{relative_log}` |
        | worktree | `{worktree}` |
        """)
    if gate_error:
        wrapper_section += f"\nWrapper exception: `{gate_error}`\n"
    if gate_details:
        failed_detail_sections: list[str] = []
        for name, ok in gates.items():
            if ok:
                continue
            detail = gate_details.get(name, "").strip()
            if not detail:
                continue
            failed_detail_sections.append(
                f"### {name}\n\n```text\n{_clip(detail, 3000)}\n```"
            )
        if failed_detail_sections:
            wrapper_section += "\n### Failed Gate Details\n\n"
            wrapper_section += "\n\n".join(failed_detail_sections)
            wrapper_section += "\n"

    if eval_path.exists():
        current = eval_path.read_text(encoding="utf-8")
        if "## Wrapper Gate Result" not in current:
            eval_path.write_text(current.rstrip() + "\n" + wrapper_section, encoding="utf-8")
        return eval_path

    title = f"# Codegen {slug(args.host)} Wrapper Eval"
    body = textwrap.dedent(f"""\
        {title}

        > **类型**：`acceptance-report`
        > **关联**：codegen wrapper / host `{args.host}`
        > **验证 spec**：`codegen-output-contract.md` §3.1
        > **作者**：codegen wrapper
        > **日期**：{date.today():%Y-%m-%d}
        > **判定**：`{verdict}`

        ## 1. 背景与目的

        opencode 未产出 eval 或未能完成可靠收口；wrapper 根据确定性 gates
        自动补写本记录，确保 red/green 结果至少沉淀到 `docs/eval-test/`。

        ## 2. 复现线索

        - worktree: `{worktree}`
        - branch: `{branch}`
        - codegen log: `{relative_log}`

        ## 3. 结论

        - **判定**：`{verdict}`
        - **失败 gates**：`{failed_text}`
        """)
    eval_path.write_text(body.rstrip() + "\n" + wrapper_section, encoding="utf-8")
    return eval_path


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
    ap.add_argument(
        "--max-red-iterations",
        type=int,
        default=3,
        help="wrapper gate red 后自动把失败证据回喂 agent 的最大次数",
    )
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
                    worktree,
                    args.model,
                    log_file,
                    feedback_file=feedback_file,
                )
                print(f"\n[codegen] opencode exit code: {opencode_rc}")
                if opencode_rc != 0:
                    print("opencode 失败；仍继续跑 wrapper gates → ", worktree)

            # 跑验收门，无论 opencode 退出码如何（agent 退出码不可信）
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
                worktree,
                args,
                GateRunResult(gates, gate_details),
                attempt,
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
    finally:
        if claimed_task is not None:
            mark_codegen_task_finished(
                args.task_db,
                task_id=claimed_task.task_id,
                success=overall,
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
