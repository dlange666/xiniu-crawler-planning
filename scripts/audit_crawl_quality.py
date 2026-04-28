#!/usr/bin/env python3
"""crawl_raw 质量审计：确定性指标 + cohort 分布 + 阈值卡。

用途：codegen 跑完 live smoke 后立即调用，把"判定 green/red"从 agent
手里抽走，避免 confirmation bias。退出码 0=pass，1=fail。

用法：
    uv run python scripts/audit_crawl_quality.py --task-id 8888 \\
        --thresholds title_rate=0.95,body_500_rate=0.70,metadata_rate=0.30

阈值由调用方传入（不同业务域的"合格"标准不同）；缺省阈值见 DEFAULT_THRESHOLDS。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_THRESHOLDS: dict[str, float] = {
    "title_rate": 0.95,        # title 非空记录占比
    "body_500_rate": 0.70,     # body_text >= 500 字记录占比
    "metadata_rate": 0.30,     # source_metadata.raw 非空记录占比
    # url 发现层
    "list_pages_min": 1,       # list_pages_fetched 至少这么多（翻页若适用）
    "host_min": 1,             # 抓到内容的不同 host 数（跨子域必备时调高）
}


def parse_thresholds(s: str | None) -> dict[str, float]:
    if not s:
        return {}
    out: dict[str, float] = {}
    for kv in s.split(","):
        if not kv.strip():
            continue
        k, v = kv.split("=", 1)
        out[k.strip()] = float(v.strip())
    return out


def audit(*, db_path: Path, task_id: int) -> dict:
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT url, host, length(data) AS dlen, data "
        "FROM crawl_raw WHERE task_id=? ORDER BY length(data)",
        (task_id,),
    ).fetchall()

    if not rows:
        return {"records": 0, "verdict": "fail", "reason": "no records"}

    n = len(rows)
    metrics = {
        "title_filled": 0,
        "body_300": 0,
        "body_500": 0,
        "body_1000": 0,
        "metadata_filled": 0,
        "attachments_found": 0,
        "interpret_links_found": 0,
    }
    body_lens: list[int] = []
    short_body_samples: list[tuple[str, int, str]] = []
    host_counter: Counter[str] = Counter()
    cohort: dict[str, list[int]] = defaultdict(list)  # host → body lengths

    for url, host, dlen, data in rows:
        d = json.loads(data)
        title = d.get("title", "")
        body = d.get("body_text", "")
        bl = len(body)
        body_lens.append(bl)
        host_counter[host] += 1
        cohort[host].append(bl)

        if title.strip():
            metrics["title_filled"] += 1
        if bl >= 300:
            metrics["body_300"] += 1
        if bl >= 500:
            metrics["body_500"] += 1
        if bl >= 1000:
            metrics["body_1000"] += 1

        # 兼容两种 metadata 形态：dict 直放 / SourceMetadata.raw 嵌套
        meta = d.get("source_metadata") or {}
        if isinstance(meta, dict):
            raw = meta.get("raw") if "raw" in meta else meta
            if raw and isinstance(raw, dict) and len(raw) > 0:
                metrics["metadata_filled"] += 1

        if d.get("attachments"):
            metrics["attachments_found"] += 1
        # data_payload 可能用 _count 形式（runner.py 当前的写法）
        if d.get("interpret_links_count", 0) > 0 or d.get("interpret_links"):
            metrics["interpret_links_found"] += 1

        if bl < 300:
            short_body_samples.append((url, bl, title[:40]))

    rates = {
        "title_rate": metrics["title_filled"] / n,
        "body_300_rate": metrics["body_300"] / n,
        "body_500_rate": metrics["body_500"] / n,
        "body_1000_rate": metrics["body_1000"] / n,
        "metadata_rate": metrics["metadata_filled"] / n,
        "attachments_rate": metrics["attachments_found"] / n,
        "interpret_rate": metrics["interpret_links_found"] / n,
    }

    return {
        "records": n,
        "rates": rates,
        "body_len_stats": {
            "min": min(body_lens),
            "max": max(body_lens),
            "mean": sum(body_lens) / n,
            "median": sorted(body_lens)[n // 2],
        },
        "host_count": len(host_counter),
        "host_distribution": dict(host_counter.most_common()),
        "cohort_quality": {
            h: {
                "n": len(lens),
                "median_body_len": sorted(lens)[len(lens) // 2],
                "low_quality_count": sum(1 for x in lens if x < 300),
            }
            for h, lens in cohort.items()
        },
        "short_body_samples": short_body_samples[:5],
    }


def evaluate(report: dict, thresholds: dict[str, float]) -> tuple[str, list[str]]:
    """对照阈值判定。返回 (verdict, failed_checks)。"""
    if report.get("records", 0) == 0:
        return "fail", ["no records"]
    rates = report["rates"]
    fails: list[str] = []
    for key, threshold in thresholds.items():
        if key in rates:
            actual = rates[key]
            if actual < threshold:
                fails.append(f"{key}: {actual:.1%} < {threshold:.1%}")
        elif key == "list_pages_min":
            # 这里需要从 fetch_record 推 list_pages_fetched；暂留 hook
            pass
        elif key == "host_min":
            if report["host_count"] < threshold:
                fails.append(
                    f"host_count: {report['host_count']} < {int(threshold)}"
                )
    return ("pass" if not fails else "fail"), fails


def render(report: dict, verdict: str, fails: list[str]) -> str:
    out: list[str] = []
    out.append(f"=== crawl_raw quality audit ===")
    out.append(f"records: {report['records']}")
    if report["records"] == 0:
        out.append(f"reason:  {report.get('reason', 'no records')}")
        out.append(f"\n=== VERDICT: {verdict.upper()} ===")
        if fails:
            out.append("failed checks:")
            for f in fails:
                out.append(f"  - {f}")
        return "\n".join(out)
    out.append(f"hosts:   {report['host_count']}  ({report['host_distribution']})")
    out.append("")
    out.append("--- field hit rates ---")
    for k, v in report["rates"].items():
        out.append(f"  {k:>20}: {v:6.1%}")
    out.append("")
    out.append("--- body_len stats ---")
    bs = report["body_len_stats"]
    out.append(
        f"  min={bs['min']}  median={bs['median']}  "
        f"mean={bs['mean']:.0f}  max={bs['max']}")
    out.append("")
    if report["short_body_samples"]:
        out.append("--- short body (<300 chars) samples ---")
        for url, bl, title in report["short_body_samples"]:
            out.append(f"  {bl:>4} chars | {title} | {url[:70]}")
        out.append("")
    out.append("--- per-host cohort quality ---")
    for h, q in report["cohort_quality"].items():
        out.append(
            f"  {h}: n={q['n']}  median_body={q['median_body_len']}  "
            f"low_quality={q['low_quality_count']}")
    out.append("")
    out.append(f"=== VERDICT: {verdict.upper()} ===")
    if fails:
        out.append("failed checks:")
        for f in fails:
            out.append(f"  - {f}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", type=int, required=True)
    ap.add_argument(
        "--db",
        default=os.getenv("CRAWLER_DB_PATH", "runtime/db/dev.db"),
    )
    ap.add_argument(
        "--thresholds",
        default=None,
        help="逗号分隔的 k=v 列表覆盖默认阈值",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 而不是人类可读格式",
    )
    args = ap.parse_args()

    thresholds = {**DEFAULT_THRESHOLDS, **parse_thresholds(args.thresholds)}
    report = audit(db_path=Path(args.db), task_id=args.task_id)
    verdict, fails = evaluate(report, thresholds)

    if args.json:
        print(json.dumps(
            {"report": report, "verdict": verdict, "failed_checks": fails,
             "thresholds": thresholds},
            ensure_ascii=False, indent=2))
    else:
        print(render(report, verdict, fails))

    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
