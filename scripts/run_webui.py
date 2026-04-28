#!/usr/bin/env python3
"""Run xiniu-crawler WebUI."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webui.app import create_app  # noqa: E402
from webui.config import WebuiConfig  # noqa: E402


def main() -> int:
    config = WebuiConfig.from_env()
    app = create_app(config)
    uvicorn.run(app, host=config.bind, port=config.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
