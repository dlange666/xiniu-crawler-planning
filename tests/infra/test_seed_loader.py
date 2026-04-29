from __future__ import annotations

from pathlib import Path

from infra.crawl.seed_loader import load_seed


def test_load_seed_defaults_politeness_rps_to_one(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.yaml"
    seed_path.write_text(
        """
host: example.gov.cn
entry_urls:
  - https://example.gov.cn/
""",
        encoding="utf-8",
    )

    seed = load_seed(seed_path)

    assert seed.politeness_rps == 1.0
