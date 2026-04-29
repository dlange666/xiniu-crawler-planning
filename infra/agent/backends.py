"""Coding agent backend implementations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AgentRunRequest:
    worktree: Path
    prompt: str
    model: str | None = None
    files: tuple[Path, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunResult:
    ok: bool
    stdout: str
    stderr: str = ""
    exit_code: int = 0


class CodingAgentBackend(Protocol):
    def run(self, request: AgentRunRequest) -> AgentRunResult:
        """Execute one coding-agent request."""
        ...


class MockAgentBackend:
    def __init__(self, results: list[AgentRunResult] | None = None) -> None:
        self.results = list(results or [AgentRunResult(ok=True, stdout="mock ok")])
        self.requests: list[AgentRunRequest] = []

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.requests.append(request)
        if not self.results:
            return AgentRunResult(ok=True, stdout="mock ok")
        return self.results.pop(0)


class OpenCodeBackend:
    def __init__(self, *, executable: str = "opencode") -> None:
        self.executable = executable

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        cmd = [self.executable, "run", request.prompt]
        if request.model:
            cmd.extend(["-m", request.model])
        for file in request.files:
            cmd.extend(["-f", str(file)])

        proc = subprocess.run(
            cmd,
            cwd=request.worktree,
            capture_output=True,
            text=True,
            check=False,
        )
        return AgentRunResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )
