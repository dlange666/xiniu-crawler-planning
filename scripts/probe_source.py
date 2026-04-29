#!/usr/bin/env python3
"""Probe a source URL with controlled fetch/render capability selection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra.source_probe import probe_url  # noqa: E402


def _slug(host: str) -> str:
    return host.replace("www.", "").replace(".", "_").replace("-", "_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--host", default=None)
    parser.add_argument(
        "--mode",
        choices=["auto", "static", "json_api", "headless"],
        default="auto",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    host = args.host or urlparse(args.url).netloc
    if not host:
        parser.error("--url must include a host, or pass --host")
    out_dir = args.out or Path("runtime/probe") / _slug(host)

    result = probe_url(url=args.url, host=host, out_dir=out_dir, mode=args.mode)
    print(result.to_json())
    return 0 if result.verdict in {"static_html", "json_api", "headless_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
