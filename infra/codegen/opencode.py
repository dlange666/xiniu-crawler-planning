"""调用 opencode CLI 的薄封装。"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


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
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).rstrip()
            if clean:
                print(f"  [agent] {clean[:140]}")
        return proc.wait()
