from __future__ import annotations

from pathlib import Path

from infra.adapter_contract import validate_golden_artifacts


def test_gov_policy_golden_fixtures_match_contract() -> None:
    root = Path(__file__).resolve().parents[2] / "tests/domains/gov_policy"
    fixture_dirs = sorted(path / "fixtures" for path in root.iterdir() if path.is_dir())

    assert fixture_dirs
    failures: list[str] = []
    for fixture_dir in fixture_dirs:
        if not fixture_dir.exists():
            continue
        ok, message = validate_golden_artifacts(fixture_dir, fixture_dir.parent.name)
        if not ok:
            failures.append(f"{fixture_dir.parent.name}: {message}")

    assert not failures
