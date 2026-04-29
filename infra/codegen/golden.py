"""Golden HTML / JSON 配对覆盖度校验。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _has_pagination_signal(payload: Any) -> bool:
    """检测 golden JSON 是否声明了非空分页结果。

    只看 `payload["parse_list"]["next_pages"]` 这条精确路径，避免不相关的
    嵌套结构被误判为分页信号。
    """
    if not isinstance(payload, dict):
        return False
    parse_list = payload.get("parse_list")
    if not isinstance(parse_list, dict):
        return False
    next_pages = parse_list.get("next_pages")
    return isinstance(next_pages, list) and len(next_pages) > 0


def validate_golden_artifacts(artifacts_dir: Path, host_slug: str) -> tuple[bool, str]:
    """按覆盖度（不是文件数）校验 golden 配对。"""
    html_files = sorted(artifacts_dir.glob(f"{host_slug}_golden_*.html"))
    json_files = sorted(artifacts_dir.glob(f"{host_slug}_golden_*.golden.json"))
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
        if _has_pagination_signal(payload):
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
