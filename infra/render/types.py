"""Render pool value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RenderBlockedPolicy = Literal[
    "disabled",
    "robots_disallow",
    "anti_bot",
    "auth_required",
    "paywall",
    "challenge",
    "budget_exceeded",
]


@dataclass(frozen=True)
class RenderDecision:
    allowed: bool
    reason: str
    render_required: bool = False
    blocked_policy: RenderBlockedPolicy | None = None


@dataclass(frozen=True)
class RenderRequest:
    url: str
    host: str
    html: str | None = None
    reason: str = "adapter_signal"
    timeout_ms: int = 15_000
    max_bytes: int = 2_000_000


@dataclass(frozen=True)
class RenderResult:
    url: str
    final_url: str
    status_code: int
    html: str
    elapsed_ms: int
    rendered: bool = True
    content_type: str = "text/html; charset=utf-8"
    error_kind: str | None = None
    error_detail: str | None = None
    bytes_received: int | None = None
    network_summary: dict[str, int | str] = field(default_factory=dict)
