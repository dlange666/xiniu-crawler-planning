from __future__ import annotations

import sys
from pathlib import Path

from infra.harness import CommandGate, CommandHarness, ComplianceScanner


def test_command_harness_reports_failed_gate(tmp_path: Path) -> None:
    harness = CommandHarness((
        CommandGate("ok", (sys.executable, "-c", "print('ok')")),
        CommandGate("bad", (sys.executable, "-c", "raise SystemExit(2)")),
    ))

    result = harness.run(tmp_path)

    assert result.ok is False
    assert result.failed_gate_names == ("bad",)


def test_compliance_scanner_blocks_forbidden_terms(tmp_path: Path) -> None:
    path = tmp_path / "adapter.py"
    path.write_text("import undetected_chromedriver\n", encoding="utf-8")

    result = ComplianceScanner().scan_files((path,))

    assert result.ok is False
    assert "undetected_chromedriver" in result.output
