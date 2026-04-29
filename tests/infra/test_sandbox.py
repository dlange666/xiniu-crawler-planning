from __future__ import annotations

import pytest

from infra.sandbox import SandboxViolation, tier1_create_host_policy


def test_tier1_policy_allows_only_source_delivery_paths() -> None:
    policy = tier1_create_host_policy(context="gov_policy", source="miit")

    policy.ensure_allowed([
        "domains/gov_policy/miit/miit_adapter.py",
        "domains/gov_policy/miit/miit_seed.yaml",
        "tests/domains/gov_policy/miit/fixtures/miit_golden_list_1.html",
        "tests/domains/gov_policy/miit/test_adapter.py",
    ])

    with pytest.raises(SandboxViolation):
        policy.ensure_allowed(["infra/http/client.py"])
