"""Simple file-content compliance scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .types import HarnessGateResult

DEFAULT_BLOCKLIST: tuple[str, ...] = (
    r"2captcha",
    r"anti-captcha",
    r"capsolver",
    r"undetected_chromedriver",
    r"playwright-stealth",
    r"selenium-stealth",
    r"captcha_solver",
    r"navigator\.webdriver\s*=\s*false",
)


@dataclass(frozen=True)
class ComplianceScanner:
    patterns: tuple[str, ...] = DEFAULT_BLOCKLIST

    def scan_files(self, files: list[Path] | tuple[Path, ...]) -> HarnessGateResult:
        hits: list[str] = []
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in self.patterns]
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in compiled:
                if pattern.search(text):
                    hits.append(f"{path}: {pattern.pattern}")
        return HarnessGateResult(
            name="compliance_blocklist",
            ok=not hits,
            output="\n".join(hits),
        )
