"""子进程执行 helper。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    output: str


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


def sh_capture(
    cmd: list[str], *, cwd: Path | None = None,
    env: dict[str, str] | None = None,
    echo: bool = True,
) -> CommandResult:
    if echo:
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


def clip(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]
