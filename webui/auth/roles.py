"""Role checks."""

from __future__ import annotations

ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def has_role(actual: str, required: str) -> bool:
    return ROLE_RANK.get(actual, -1) >= ROLE_RANK[required]

