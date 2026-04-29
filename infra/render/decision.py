"""Render decision gate.

This module only decides whether rendering may be attempted. It never tries to
work around protected states such as captcha, login, paywalls, or challenges.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .config import RenderConfig
from .types import RenderDecision

_AUTH_RE = re.compile(r"(login|signin|auth_required|登录|请登录)", re.IGNORECASE)
_PAYWALL_RE = re.compile(r"(paywall|subscribe|付费|订阅后|会员)", re.IGNORECASE)
_CHALLENGE_RE = re.compile(
    r"(captcha|recaptcha|cf_chl_|just a moment|challenge|验证码|安全验证|滑块)",
    re.IGNORECASE,
)


def decide_render(
    *,
    html: str,
    url: str,
    render_mode: str = "direct",
    config: RenderConfig | None = None,
    should_render: Callable[[str, str], bool] | None = None,
    parse_failed: bool = False,
    robots_allowed: bool = True,
    anti_bot_signal: str | None = None,
) -> RenderDecision:
    """Return the guarded render decision for one fetched page."""
    config = config or RenderConfig.from_env()
    if not robots_allowed:
        return RenderDecision(
            allowed=False,
            render_required=False,
            reason="robots_disallow",
            blocked_policy="robots_disallow",
        )
    if anti_bot_signal:
        return RenderDecision(
            allowed=False,
            render_required=False,
            reason=f"anti_bot:{anti_bot_signal}",
            blocked_policy="anti_bot",
        )
    protected = _protected_policy(html)
    if protected is not None:
        return RenderDecision(
            allowed=False,
            render_required=False,
            reason=f"protected:{protected}",
            blocked_policy=protected,
        )

    signal = _render_signal(
        html=html,
        url=url,
        render_mode=render_mode,
        should_render=should_render,
        parse_failed=parse_failed,
    )
    if signal is None:
        return RenderDecision(allowed=False, reason="no_render_signal")
    if not config.enabled:
        return RenderDecision(
            allowed=False,
            render_required=True,
            reason="render_disabled",
            blocked_policy="disabled",
        )
    return RenderDecision(allowed=True, render_required=True, reason=signal)


def _render_signal(
    *,
    html: str,
    url: str,
    render_mode: str,
    should_render: Callable[[str, str], bool] | None,
    parse_failed: bool,
) -> str | None:
    if render_mode == "headless":
        return "adapter_render_mode"
    if should_render is not None and should_render(html, url):
        return "adapter_should_render"
    if parse_failed:
        return "parse_failed_fallback"
    return None


def _protected_policy(html: str) -> str | None:
    if _AUTH_RE.search(html):
        return "auth_required"
    if _PAYWALL_RE.search(html):
        return "paywall"
    if _CHALLENGE_RE.search(html):
        return "challenge"
    return None
