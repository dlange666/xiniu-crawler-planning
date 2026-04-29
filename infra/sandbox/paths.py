"""Path allowlist checks for codegen sandboxes."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


class SandboxViolation(ValueError):
    pass


@dataclass(frozen=True)
class WritePolicy:
    name: str
    allowed: tuple[str, ...]

    def is_allowed(self, path: Path | str) -> bool:
        normalized = _normalize(path)
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.allowed)

    def ensure_allowed(self, paths: list[Path | str] | tuple[Path | str, ...]) -> None:
        denied = [str(path) for path in paths if not self.is_allowed(path)]
        if denied:
            msg = f"{self.name} denied paths: {', '.join(denied)}"
            raise SandboxViolation(msg)


def tier1_create_host_policy(*, context: str, source: str) -> WritePolicy:
    return WritePolicy(
        name=f"tier1_create_host:{context}/{source}",
        allowed=(
            f"domains/{context}/{source}/{source}_adapter.py",
            f"domains/{context}/{source}/{source}_seed.yaml",
            f"tests/domains/{context}/{source}/fixtures/{source}_golden_*",
            f"tests/domains/{context}/{source}/test_adapter.py",
            "docs/exec-plan/active/plan-*.md",
            "docs/task/active/task-*.json",
            "docs/eval-test/*.md",
        ),
    )


def _normalize(path: Path | str) -> str:
    return str(path).replace("\\", "/").lstrip("./")
