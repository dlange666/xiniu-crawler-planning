"""Offline adapter contract verification helpers.

This package is intentionally separate from ``infra/crawl``: it validates
adapter deliverables for tests and codegen gates, but is not part of the
crawler execution path.
"""

from __future__ import annotations

from .golden import golden_fixture_dir, validate_golden_artifacts

__all__ = ["golden_fixture_dir", "validate_golden_artifacts"]
