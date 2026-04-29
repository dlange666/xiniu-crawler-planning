"""Render pool configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class RenderConfig:
    enabled: bool = False
    max_concurrency: int = 1
    per_host_concurrency: int = 1
    page_timeout_ms: int = 15_000
    max_bytes: int = 2_000_000
    queue_max_size: int = 100

    @classmethod
    def from_env(cls) -> RenderConfig:
        """Load conservative render defaults from environment."""
        return cls(
            enabled=_env_bool("RENDER_POOL_ENABLED", False),
            max_concurrency=_env_int("RENDER_POOL_MAX_CONCURRENCY", 1),
            per_host_concurrency=_env_int("RENDER_POOL_PER_HOST_CONCURRENCY", 1),
            page_timeout_ms=_env_int("RENDER_PAGE_TIMEOUT_MS", 15_000),
            max_bytes=_env_int("RENDER_MAX_BYTES", 2_000_000),
            queue_max_size=_env_int("RENDER_QUEUE_MAX_SIZE", 100),
        )
