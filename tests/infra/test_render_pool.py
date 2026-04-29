from __future__ import annotations

from infra.render import (
    PassthroughBackend,
    RenderConfig,
    RendererPool,
    RenderRequest,
    decide_render,
)
from infra.render.types import RenderResult


def test_decision_blocks_render_when_disabled() -> None:
    decision = decide_render(
        html="<div id='app'></div>",
        url="https://example.com/app",
        render_mode="headless",
        config=RenderConfig(enabled=False),
    )

    assert decision.render_required is True
    assert decision.allowed is False
    assert decision.blocked_policy == "disabled"


def test_decision_blocks_protected_pages_even_when_enabled() -> None:
    decision = decide_render(
        html="<html>captcha required</html>",
        url="https://example.com/protected",
        render_mode="headless",
        config=RenderConfig(enabled=True),
    )

    assert decision.allowed is False
    assert decision.blocked_policy == "challenge"


def test_decision_allows_adapter_signal_when_enabled() -> None:
    decision = decide_render(
        html="<div id='app'></div>",
        url="https://example.com/app",
        config=RenderConfig(enabled=True),
        should_render=lambda html, url: "id='app'" in html,
    )

    assert decision.allowed is True
    assert decision.reason == "adapter_should_render"


def test_pool_returns_disabled_failure_by_default() -> None:
    pool = RendererPool(
        backend=PassthroughBackend(),
        config=RenderConfig(enabled=False),
    )

    result = pool.render(RenderRequest(url="https://example.com/", host="example.com"))

    assert result.error_kind == "render_disabled"


def test_pool_enforces_max_bytes() -> None:
    class LargeBackend:
        def render(self, request: RenderRequest) -> RenderResult:
            return RenderResult(
                url=request.url,
                final_url=request.url,
                status_code=200,
                html="x" * 20,
                elapsed_ms=1,
                bytes_received=20,
            )

    pool = RendererPool(
        backend=LargeBackend(),
        config=RenderConfig(enabled=True, max_bytes=10),
    )

    result = pool.render(RenderRequest(
        url="https://example.com/",
        host="example.com",
        max_bytes=10,
    ))

    assert result.error_kind == "render_bytes_exceeded"
    assert result.bytes_received == 20
