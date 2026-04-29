"""Command-based harness runner."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .types import HarnessGateResult, HarnessResult


@dataclass(frozen=True)
class CommandGate:
    name: str
    command: tuple[str, ...]


class CommandHarness:
    def __init__(self, gates: tuple[CommandGate, ...]) -> None:
        self.gates = gates

    def run(self, worktree: Path) -> HarnessResult:
        results: list[HarnessGateResult] = []
        for gate in self.gates:
            proc = subprocess.run(
                list(gate.command),
                cwd=worktree,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            results.append(HarnessGateResult(
                name=gate.name,
                ok=proc.returncode == 0,
                output=proc.stdout,
            ))
        return HarnessResult(tuple(results))
