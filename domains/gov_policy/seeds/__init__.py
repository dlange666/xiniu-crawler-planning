"""Seed 加载器：YAML → SeedSpec。"""

from __future__ import annotations

from pathlib import Path

import yaml

from domains.gov_policy.model import SeedSpec


def load_seed(yaml_path: Path) -> SeedSpec:
    with Path(yaml_path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return SeedSpec(
        host=data["host"],
        entry_urls=list(data["entry_urls"]),
        politeness_rps=float(data.get("politeness_rps", 0.5)),
        max_pages_per_run=data.get("max_pages_per_run"),
        crawl_mode=data.get("crawl_mode", "full"),
    )
