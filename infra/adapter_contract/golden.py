"""Golden fixture contract helpers for adapter tests and codegen gates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def golden_fixture_dir(repo_root: Path, business_context: str, source_slug: str) -> Path:
    """Return the canonical fixture directory for a source adapter."""
    return (
        Path(repo_root)
        / "tests"
        / "domains"
        / business_context
        / source_slug
        / "fixtures"
    )


def validate_golden_artifacts(artifacts_dir: Path, source_slug: str) -> tuple[bool, str]:
    """Validate coverage-oriented golden files instead of plain file counts."""
    html_files = sorted(artifacts_dir.glob(f"{source_slug}_golden_*.html"))
    json_files = sorted(artifacts_dir.glob(f"{source_slug}_golden_*.golden.json"))
    html_by_stem = {p.with_suffix("").name: p for p in html_files}
    json_by_stem = {p.name.removesuffix(".golden.json"): p for p in json_files}
    paired_stems = sorted(set(html_by_stem) & set(json_by_stem))
    missing_json = sorted(set(html_by_stem) - set(json_by_stem))
    missing_html = sorted(set(json_by_stem) - set(html_by_stem))
    if missing_json:
        return False, f"missing paired golden JSON for: {', '.join(missing_json[:5])}"
    if missing_html:
        return False, f"missing paired golden HTML for: {', '.join(missing_html[:5])}"

    list_pairs = 0
    detail_pairs = 0
    pagination_pairs = 0
    pagination_signal = False
    invalid_json: list[str] = []
    for stem in paired_stems:
        json_path = json_by_stem[stem]
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            invalid_json.append(f"{json_path.name}: {exc.msg}")
            continue
        if "_golden_list_" in stem or stem.endswith("_golden_list"):
            list_pairs += 1
        if "_golden_detail_" in stem or stem.endswith("_golden_detail"):
            detail_pairs += 1
        if re.search(r"_golden_list_(?:[2-9]|\d{2,})$", stem) or "pagination" in stem:
            pagination_pairs += 1
        if _json_contains_key(payload, "parse_list") and _json_has_nonempty_next_pages(payload):
            pagination_signal = True

    if invalid_json:
        return False, "; ".join(invalid_json[:3])
    if len(paired_stems) < 4:
        return False, f"paired golden count={len(paired_stems)}, required>=4"
    if list_pairs < 1:
        return False, "required >=1 paired list golden"
    if detail_pairs < 3:
        return False, f"paired detail golden count={detail_pairs}, required>=3"
    if pagination_signal and pagination_pairs < 1:
        return False, "pagination signal found, required >=1 paired pagination/list_2 golden"
    return True, (
        f"paired={len(paired_stems)}, list={list_pairs}, detail={detail_pairs}, "
        f"pagination={pagination_pairs}"
    )


def _json_contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_json_contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_json_contains_key(v, key) for v in value)
    return False


def _json_has_nonempty_next_pages(value: Any) -> bool:
    if isinstance(value, dict):
        next_pages = value.get("next_pages")
        if isinstance(next_pages, list) and len(next_pages) > 0:
            return True
        return any(_json_has_nonempty_next_pages(v) for v in value.values())
    if isinstance(value, list):
        return any(_json_has_nonempty_next_pages(v) for v in value)
    return False
