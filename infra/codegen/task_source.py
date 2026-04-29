"""Task source protocol for codegen workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CodegenTask:
    task_id: str
    worktree: Path
    prompt: str
    business_context: str
    source_slug: str
    host: str
    model: str | None = None
    prompt_files: tuple[Path, ...] = ()
    expected_write_paths: tuple[Path, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


class TaskSource(Protocol):
    def fetch_pending(self) -> CodegenTask | None: ...

    def claim(self, task_id: str) -> bool: ...

    def report_success(self, task_id: str, message: str) -> None: ...

    def report_failure(self, task_id: str, message: str) -> None: ...


class MemoryTaskSource:
    def __init__(self, tasks: list[CodegenTask]) -> None:
        self._pending = list(tasks)
        self.claimed: list[str] = []
        self.successes: list[tuple[str, str]] = []
        self.failures: list[tuple[str, str]] = []

    def fetch_pending(self) -> CodegenTask | None:
        return self._pending[0] if self._pending else None

    def claim(self, task_id: str) -> bool:
        if not self._pending or self._pending[0].task_id != task_id:
            return False
        self.claimed.append(task_id)
        return True

    def report_success(self, task_id: str, message: str) -> None:
        self.successes.append((task_id, message))
        self._drop(task_id)

    def report_failure(self, task_id: str, message: str) -> None:
        self.failures.append((task_id, message))
        self._drop(task_id)

    def _drop(self, task_id: str) -> None:
        self._pending = [task for task in self._pending if task.task_id != task_id]
