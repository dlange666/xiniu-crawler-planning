from __future__ import annotations

import subprocess
from pathlib import Path

from infra.agent import AgentRunRequest, AgentRunResult, MockAgentBackend, OpenCodeBackend


def test_mock_agent_records_requests(tmp_path: Path) -> None:
    backend = MockAgentBackend([AgentRunResult(ok=True, stdout="done")])
    request = AgentRunRequest(worktree=tmp_path, prompt="do work", model="m")

    result = backend.run(request)

    assert result.ok is True
    assert backend.requests == [request]


def test_opencode_backend_builds_expected_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(cmd, cwd, capture_output, text, check):  # noqa: ANN001
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backend = OpenCodeBackend(executable="opencode")
    result = backend.run(AgentRunRequest(
        worktree=tmp_path,
        prompt="execute",
        model="test-model",
        files=(Path("docs/codegen-pipeline.md"),),
    ))

    assert result.ok is True
    assert calls == [(
        [
            "opencode",
            "run",
            "execute",
            "-m",
            "test-model",
            "-f",
            "docs/codegen-pipeline.md",
        ],
        tmp_path,
    )]
