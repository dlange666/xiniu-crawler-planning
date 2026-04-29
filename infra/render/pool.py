"""Synchronous render pool wrapper."""

from __future__ import annotations

import threading
import time
from typing import Protocol

from .config import RenderConfig
from .types import RenderRequest, RenderResult


class RendererBackend(Protocol):
    def render(self, request: RenderRequest) -> RenderResult:
        """Render one URL and return HTML or a typed failure."""
        ...


class PassthroughBackend:
    """Deterministic backend for tests and dry-run wiring.

    It does not fetch or execute JavaScript; it only exercises pool behavior.
    """

    def render(self, request: RenderRequest) -> RenderResult:
        html = request.html or ""
        return RenderResult(
            url=request.url,
            final_url=request.url,
            status_code=200,
            html=html,
            elapsed_ms=0,
            bytes_received=len(html.encode("utf-8")),
            network_summary={"backend": "passthrough"},
        )


class RendererPool:
    def __init__(
        self,
        *,
        backend: RendererBackend,
        config: RenderConfig | None = None,
    ) -> None:
        self.backend = backend
        self.config = config or RenderConfig.from_env()
        self._global = threading.BoundedSemaphore(max(1, self.config.max_concurrency))
        self._host_lock = threading.Lock()
        self._host_semaphores: dict[str, threading.BoundedSemaphore] = {}

    def render(self, request: RenderRequest) -> RenderResult:
        if not self.config.enabled:
            return _failure(request, "render_disabled", "RENDER_POOL_ENABLED is false")

        request = RenderRequest(
            url=request.url,
            host=request.host,
            html=request.html,
            reason=request.reason,
            timeout_ms=min(request.timeout_ms, self.config.page_timeout_ms),
            max_bytes=min(request.max_bytes, self.config.max_bytes),
        )
        host_semaphore = self._host_semaphore(request.host)
        started = time.monotonic()
        with self._global, host_semaphore:
            result = self.backend.render(request)

        size = len(result.html.encode("utf-8"))
        if size > request.max_bytes:
            return RenderResult(
                url=request.url,
                final_url=result.final_url,
                status_code=result.status_code,
                html=result.html[: request.max_bytes],
                elapsed_ms=int((time.monotonic() - started) * 1000),
                content_type=result.content_type,
                error_kind="render_bytes_exceeded",
                error_detail=f"bytes={size} max={request.max_bytes}",
                bytes_received=size,
                network_summary=result.network_summary,
            )
        return result

    def _host_semaphore(self, host: str) -> threading.BoundedSemaphore:
        with self._host_lock:
            semaphore = self._host_semaphores.get(host)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(
                    max(1, self.config.per_host_concurrency)
                )
                self._host_semaphores[host] = semaphore
            return semaphore


def _failure(request: RenderRequest, kind: str, detail: str) -> RenderResult:
    return RenderResult(
        url=request.url,
        final_url=request.url,
        status_code=0,
        html="",
        elapsed_ms=0,
        error_kind=kind,
        error_detail=detail,
        bytes_received=0,
    )
