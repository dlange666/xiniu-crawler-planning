#!/usr/bin/env python3
"""CLI 入口：从 seed YAML 起跑一个采集 task。

用法：
    uv run scripts/run_crawl_task.py domains/gov_policy/ndrc/ndrc_seed.yaml

环境变量：
    STORAGE_PROFILE=dev (默认)
    CRAWLER_DB_PATH=runtime/db/dev.db
    CRAWLER_BLOB_ROOT=runtime/raw

任务 ID：每次运行用当前时间戳生成（MVP 单进程，本仓库不持有 task 主表）。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# 让 scripts/ 能 import 仓库根的包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra import adapter_registry  # noqa: E402
from infra.crawl import CrawlEngine, TaskSpec, load_seed  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a crawl task from a seed YAML.")
    parser.add_argument("seed_yaml", help="path to seed YAML")
    parser.add_argument("--task-id", type=int, default=None,
                        help="task id (default: timestamp)")
    parser.add_argument("--strategy", choices=["bfs", "dfs"], default="bfs")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=None,
                        help="override seed.max_pages_per_run")
    parser.add_argument("--scope-mode",
                        choices=["same_origin", "same_etld_plus_one",
                                 "url_pattern", "allowlist"],
                        default="same_origin")
    parser.add_argument("--scope-url-pattern", default=None)
    parser.add_argument("--business-context", default="gov_policy")
    args = parser.parse_args()

    seed = load_seed(Path(args.seed_yaml))
    task_id = args.task_id or int(time.time())
    task = TaskSpec(
        task_id=task_id,
        business_context=args.business_context,
        site_url=seed.entry_urls[0],
        data_kind="policy",
        max_pages_per_run=args.max_pages or seed.max_pages_per_run,
        politeness_rps=seed.politeness_rps,
        crawl_mode=seed.crawl_mode,  # type: ignore[arg-type]
        strategy=args.strategy,
        max_depth=args.max_depth,
        scope_mode=args.scope_mode,
        scope_url_pattern=args.scope_url_pattern,
    )

    print("\n=== Crawl Task ===")
    print(f"  task_id        = {task.task_id}")
    print(f"  business_ctx   = {task.business_context}")
    print(f"  host           = {seed.host}")
    print(f"  entry          = {seed.entry_urls}")
    print(f"  strategy       = {task.strategy}")
    print(f"  max_depth      = {task.max_depth}")
    print(f"  scope_mode     = {task.scope_mode}")
    print(f"  max_pages      = {task.max_pages_per_run}")
    print(f"  RPS            = {seed.politeness_rps}")
    print()

    # adapter 通过全局注册表自动解析（business_context + host）
    adapter_registry.discover()
    engine = CrawlEngine(task=task, seed=seed)
    try:
        report = engine.run()
    finally:
        engine.close()

    print("\n=== Report ===")
    print(f"  list_pages_fetched      = {report.list_pages_fetched}")
    print(f"  detail_urls_discovered  = {report.detail_urls_discovered}")
    print(f"  detail_urls_fetched     = {report.detail_urls_fetched}")
    print(f"  interpret_pages_fetched = {report.interpret_pages_fetched}")
    print(f"  attachments_fetched     = {report.attachments_fetched}")
    print(f"  raw_records_written     = {report.raw_records_written}")
    print(f"  raw_records_dedup_hit   = {report.raw_records_dedup_hit}")
    print(f"  rejected_by_scope       = {report.rejected_by_scope}")
    print(f"  rejected_by_robots      = {report.rejected_by_robots}")
    print(f"  errors                  = {report.errors}")
    print(f"  anti_bot_events         = {report.anti_bot_events}")
    if report.failures:
        print(f"  failures ({len(report.failures)}):")
        for f in report.failures[:10]:
            print(f"    - {f}")
    return 0 if report.errors == 0 and report.raw_records_written > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
