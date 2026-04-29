"""Headless rendering primitives.

The package exposes the decision and pool interfaces now. Real Playwright
execution remains opt-in through an explicit backend and disabled default
configuration.
"""

from __future__ import annotations

from .config import RenderConfig
from .decision import decide_render
from .pool import PassthroughBackend, RendererBackend, RendererPool
from .types import RenderDecision, RenderRequest, RenderResult

__all__ = [
    "PassthroughBackend",
    "RenderConfig",
    "RenderDecision",
    "RenderRequest",
    "RenderResult",
    "RendererBackend",
    "RendererPool",
    "decide_render",
]
