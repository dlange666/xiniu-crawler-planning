"""Codegen worker orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from infra.agent import AgentRunRequest, CodingAgentBackend
from infra.harness import HarnessResult
from infra.sandbox import WritePolicy

from .task_source import CodegenTask, TaskSource


class HarnessRunner(Protocol):
    def run(self, task: CodegenTask) -> HarnessResult: ...


@dataclass(frozen=True)
class WorkerRunResult:
    status: str
    task_id: str | None = None
    message: str = ""


class CodegenWorker:
    def __init__(
        self,
        *,
        task_source: TaskSource,
        agent: CodingAgentBackend,
        harness: HarnessRunner,
        write_policy: WritePolicy,
    ) -> None:
        self.task_source = task_source
        self.agent = agent
        self.harness = harness
        self.write_policy = write_policy

    def run_once(self) -> WorkerRunResult:
        task = self.task_source.fetch_pending()
        if task is None:
            return WorkerRunResult(status="idle")
        if not self.task_source.claim(task.task_id):
            return WorkerRunResult(
                status="claim_failed",
                task_id=task.task_id,
                message="task claim failed",
            )

        try:
            self.write_policy.ensure_allowed(task.expected_write_paths)
        except ValueError as exc:
            message = str(exc)
            self.task_source.report_failure(task.task_id, message)
            return WorkerRunResult(status="failed", task_id=task.task_id, message=message)

        agent_result = self.agent.run(AgentRunRequest(
            worktree=task.worktree,
            prompt=task.prompt,
            model=task.model,
            files=task.prompt_files,
            metadata=task.metadata,
        ))
        if not agent_result.ok:
            message = agent_result.stderr or agent_result.stdout
            self.task_source.report_failure(task.task_id, message)
            return WorkerRunResult(status="failed", task_id=task.task_id, message=message)

        harness_result = self.harness.run(task)
        if not harness_result.ok:
            message = "failed gates: " + ", ".join(harness_result.failed_gate_names)
            self.task_source.report_failure(task.task_id, message)
            return WorkerRunResult(status="failed", task_id=task.task_id, message=message)

        self.task_source.report_success(task.task_id, "codegen worker green")
        return WorkerRunResult(status="completed", task_id=task.task_id)
