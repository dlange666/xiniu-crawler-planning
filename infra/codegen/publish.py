"""Codegen 产物的 git 提交与推送。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from infra.codegen.paths import (
    adapter_test_artifact,
    plan_artifact_path,
    slug,
    source_dir,
    task_artifact_path,
)
from infra.codegen.shell import sh_capture


def codegen_commit_paths(
    worktree: Path,
    args: argparse.Namespace,
    *,
    eval_path: Path | None,
    overall: bool,
) -> list[Path]:
    """green：提交 plan/task/eval/源/测试；red：只提交 eval 诊断。

    red 分支不提交半成品 adapter / 测试 / golden，避免污染分支历史。
    """
    if overall:
        paths = [
            plan_artifact_path(worktree, args),
            task_artifact_path(worktree, args),
            eval_path,
            source_dir(worktree, args),
            adapter_test_artifact(worktree, args),
        ]
    else:
        paths = [eval_path]
    return [path for path in paths if path is not None and path.exists()]


def commit_and_push_codegen_result(
    *,
    worktree: Path,
    args: argparse.Namespace,
    branch: str,
    eval_path: Path | None,
    overall: bool,
) -> bool:
    paths = codegen_commit_paths(worktree, args, eval_path=eval_path, overall=overall)
    if not paths:
        print("[publish] no paths to commit")
        return False

    relative_paths = [str(path.relative_to(worktree)) for path in paths]
    print("[publish] staging paths:")
    for path in relative_paths:
        print(f"  - {path}")
    if not sh_capture(["git", "add", "--", *relative_paths], cwd=worktree).ok:
        return False

    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=worktree).returncode == 0:
        print("[publish] no staged changes; skip commit")
        return False

    host_slug = slug(args.host)
    message = (
        f"feature({host_slug}): add codegen adapter"
        if overall
        else f"docs({host_slug}): record codegen red eval"
    )
    if not sh_capture(["git", "commit", "-m", message], cwd=worktree).ok:
        return False
    return sh_capture(["git", "push", "-u", "origin", branch], cwd=worktree).ok
