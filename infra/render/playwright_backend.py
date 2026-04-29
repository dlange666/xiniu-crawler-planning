"""Optional Playwright backend.

The dependency is intentionally optional so the default test/dev path does not
install browsers. Production enablement must still go through render-pool
workflow gates and compliance checks.
"""

from __future__ import annotations

import time

from .types import RenderRequest, RenderResult


class PlaywrightBackend:
    def render(self, request: RenderRequest) -> RenderResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - dependency intentionally optional
            raise RuntimeError(
                "playwright is not installed; render pool backend is unavailable"
            ) from exc

        started = time.monotonic()
        with sync_playwright() as p:  # pragma: no cover - not run in unit tests
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(request.url, wait_until="networkidle", timeout=request.timeout_ms)
                html = page.content()
                return RenderResult(
                    url=request.url,
                    final_url=page.url,
                    status_code=200,
                    html=html,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    bytes_received=len(html.encode("utf-8")),
                    network_summary={"backend": "playwright"},
                )
            finally:
                browser.close()
