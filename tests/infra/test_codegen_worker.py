from __future__ import annotations

from pathlib import Path

from infra.agent import AgentRunResult, MockAgentBackend
from infra.codegen import CodegenTask, CodegenWorker, MemoryTaskSource
from infra.harness import HarnessGateResult, HarnessResult
from infra.sandbox import tier1_create_host_policy


class _Harness:
    def __init__(self, result: HarnessResult) -> None:
        self.result = result
        self.tasks: list[CodegenTask] = []

    def run(self, task: CodegenTask) -> HarnessResult:
        self.tasks.append(task)
        return self.result


def _task(tmp_path: Path) -> CodegenTask:
    return CodegenTask(
        task_id="T-1",
        worktree=tmp_path,
        prompt="build adapter",
        business_context="gov_policy",
        source_slug="miit",
        host="www.miit.gov.cn",
        expected_write_paths=(
            Path("domains/gov_policy/miit/miit_adapter.py"),
            Path("tests/domains/gov_policy/miit/test_adapter.py"),
        ),
    )


def test_codegen_worker_success_path(tmp_path: Path) -> None:
    source = MemoryTaskSource([_task(tmp_path)])
    harness = _Harness(HarnessResult((
        HarnessGateResult("pytest", True, "ok"),
    )))
    worker = CodegenWorker(
        task_source=source,
        agent=MockAgentBackend([AgentRunResult(ok=True, stdout="agent ok")]),
        harness=harness,
        write_policy=tier1_create_host_policy(context="gov_policy", source="miit"),
    )

    result = worker.run_once()

    assert result.status == "completed"
    assert source.successes == [("T-1", "codegen worker green")]
    assert source.failures == []
    assert harness.tasks[0].task_id == "T-1"


def test_codegen_worker_rejects_sandbox_violation(tmp_path: Path) -> None:
    bad = CodegenTask(
        task_id="T-2",
        worktree=tmp_path,
        prompt="bad",
        business_context="gov_policy",
        source_slug="miit",
        host="www.miit.gov.cn",
        expected_write_paths=(Path("infra/http/client.py"),),
    )
    source = MemoryTaskSource([bad])
    worker = CodegenWorker(
        task_source=source,
        agent=MockAgentBackend(),
        harness=_Harness(HarnessResult(())),
        write_policy=tier1_create_host_policy(context="gov_policy", source="miit"),
    )

    result = worker.run_once()

    assert result.status == "failed"
    assert "denied paths" in source.failures[0][1]


def test_codegen_worker_reports_harness_failure(tmp_path: Path) -> None:
    source = MemoryTaskSource([_task(tmp_path)])
    worker = CodegenWorker(
        task_source=source,
        agent=MockAgentBackend(),
        harness=_Harness(HarnessResult((
            HarnessGateResult("audit", False, "bad quality"),
        ))),
        write_policy=tier1_create_host_policy(context="gov_policy", source="miit"),
    )

    result = worker.run_once()

    assert result.status == "failed"
    assert source.failures == [("T-1", "failed gates: audit")]
