"""Harness result value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessGateResult:
    name: str
    ok: bool
    output: str = ""


@dataclass(frozen=True)
class HarnessResult:
    gates: tuple[HarnessGateResult, ...]

    @property
    def ok(self) -> bool:
        return all(gate.ok for gate in self.gates)

    @property
    def failed_gate_names(self) -> tuple[str, ...]:
        return tuple(gate.name for gate in self.gates if not gate.ok)
