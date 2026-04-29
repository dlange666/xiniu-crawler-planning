"""Wrapper-level eval 报告写入。"""

from __future__ import annotations

import argparse
import contextlib
import textwrap
from datetime import date, datetime
from pathlib import Path

from infra.codegen.paths import REPO, eval_artifact_path, slug
from infra.codegen.shell import clip


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
    """把 wrapper green/red 证据写到 eval-test。

    opencode 是不可信 worker：可能未写 eval 就退出，或自报 partial 而 wrapper gates
    红。最终判定权属于 wrapper，必须把证据沉淀到 docs/eval-test/。
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
                f"### {name}\n\n```text\n{clip(detail, 3000)}\n```"
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

        opencode 未产出 eval 或未能可靠收口；wrapper 根据确定性 gates 自动补写本记录，
        确保 red/green 结果至少沉淀到 `docs/eval-test/`。

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
