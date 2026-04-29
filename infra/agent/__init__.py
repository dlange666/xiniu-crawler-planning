"""Coding agent backend abstractions."""

from __future__ import annotations

from .backends import (
    AgentRunRequest,
    AgentRunResult,
    CodingAgentBackend,
    MockAgentBackend,
    OpenCodeBackend,
)

__all__ = [
    "AgentRunRequest",
    "AgentRunResult",
    "CodingAgentBackend",
    "MockAgentBackend",
    "OpenCodeBackend",
]
