"""Controlled source probing for codegen.

The probe is the only place where codegen should discover static HTML vs JSON
API vs headless requirements. It goes through shared HTTP/robots controls and
writes replayable artifacts under the caller-provided output directory.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

from infra.http import HttpClient
from infra.robots import RobotsChecker

ProbeVerdict = Literal[
    "static_html",
    "json_api",
    "headless_required",
    "robots_disallow",
    "blocked",
    "fetch_failed",
]

ProbeMode = Literal["auto", "static", "json_api", "headless"]


@dataclass(frozen=True)
class ProbeFetchResult:
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    error_kind: str | None = None
    error_detail: str | None = None
    anti_bot_signal: str | None = None


@dataclass(frozen=True)
class ProbeArtifact:
    name: str
    path: str
    url: str
    status_code: int
    content_type: str | None
    bytes_written: int


@dataclass(frozen=True)
class ProbeResult:
    verdict: ProbeVerdict
    entry_url: str
    final_url: str
    recommended_source_url: str | None = None
    render_required: bool = False
    anti_bot_detected: bool = False
    blocked_reason: str | None = None
    signals: list[str] = field(default_factory=list)
    artifacts: list[ProbeArtifact] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


FetchFn = Callable[[str, str], ProbeFetchResult]
RobotsFn = Callable[[str], tuple[bool, str]]


class SourceProbe:
    def __init__(self, *, fetch: FetchFn, robots_allowed: RobotsFn | None = None) -> None:
        self._fetch = fetch
        self._robots_allowed = robots_allowed

    def probe(
        self,
        *,
        url: str,
        host: str,
        out_dir: Path,
        mode: ProbeMode = "auto",
    ) -> ProbeResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        allowed, robots_reason = self._check_robots(url)
        if not allowed:
            result = ProbeResult(
                verdict="robots_disallow",
                entry_url=url,
                final_url=url,
                render_required=False,
                blocked_reason=robots_reason,
                signals=[f"robots:{robots_reason}"],
            )
            self._write_result(out_dir, result)
            return result

        entry = self._fetch(url, host)
        artifacts = [
            self._write_artifact(out_dir, "entry", entry, _extension_for(entry, fallback=".html"))
        ]
        signals: list[str] = [f"robots:{robots_reason}", f"entry_status:{entry.status_code}"]

        if entry.anti_bot_signal:
            result = ProbeResult(
                verdict="blocked",
                entry_url=url,
                final_url=entry.final_url,
                anti_bot_detected=True,
                blocked_reason=entry.anti_bot_signal,
                signals=[*signals, f"anti_bot:{entry.anti_bot_signal}"],
                artifacts=artifacts,
            )
            self._write_result(out_dir, result)
            return result

        if entry.status_code == 0 or entry.status_code >= 400 or entry.error_kind:
            result = ProbeResult(
                verdict="fetch_failed",
                entry_url=url,
                final_url=entry.final_url,
                blocked_reason=entry.error_kind or f"http_{entry.status_code}",
                signals=[*signals, f"error:{entry.error_detail or entry.error_kind}"],
                artifacts=artifacts,
            )
            self._write_result(out_dir, result)
            return result

        if _looks_like_json(entry):
            result = ProbeResult(
                verdict="json_api",
                entry_url=url,
                final_url=entry.final_url,
                recommended_source_url=entry.final_url,
                signals=[*signals, "entry_is_json"],
                artifacts=artifacts,
            )
            self._write_result(out_dir, result)
            return result

        html = entry.body.decode(_encoding(entry), errors="replace")
        redirect_url = _detect_js_redirect(html, entry.final_url)
        if redirect_url and mode in ("auto", "static", "json_api"):
            redirected = self._fetch(redirect_url, host)
            artifacts.append(
                self._write_artifact(
                    out_dir, "redirected", redirected, _extension_for(redirected, fallback=".html")
                )
            )
            signals.append(f"js_redirect:{redirect_url}")
            if redirected.status_code < 400 and not redirected.anti_bot_signal:
                entry = redirected
                html = redirected.body.decode(_encoding(redirected), errors="replace")

        if mode == "headless":
            result = ProbeResult(
                verdict="headless_required",
                entry_url=url,
                final_url=entry.final_url,
                render_required=True,
                blocked_reason="headless_probe_not_implemented",
                signals=[*signals, "headless_requested"],
                artifacts=artifacts,
            )
            self._write_result(out_dir, result)
            return result

        json_candidate = self._probe_json_candidates(
            html=html,
            base_url=entry.final_url,
            host=host,
            out_dir=out_dir,
            artifacts=artifacts,
            signals=signals,
            enabled=mode in ("auto", "json_api"),
        )
        if json_candidate is not None:
            result = ProbeResult(
                verdict="json_api",
                entry_url=url,
                final_url=entry.final_url,
                recommended_source_url=json_candidate.final_url,
                signals=[*signals, "json_candidate_ok"],
                artifacts=artifacts,
            )
            self._write_result(out_dir, result)
            return result

        if _looks_like_js_shell(html):
            result = ProbeResult(
                verdict="headless_required",
                entry_url=url,
                final_url=entry.final_url,
                render_required=True,
                signals=[*signals, "js_shell_detected"],
                artifacts=artifacts,
            )
            self._write_result(out_dir, result)
            return result

        result = ProbeResult(
            verdict="static_html",
            entry_url=url,
            final_url=entry.final_url,
            recommended_source_url=entry.final_url,
            signals=[*signals, "static_html_candidate"],
            artifacts=artifacts,
        )
        self._write_result(out_dir, result)
        return result

    def _check_robots(self, url: str) -> tuple[bool, str]:
        if self._robots_allowed is None:
            return True, "not_checked"
        return self._robots_allowed(url)

    def _probe_json_candidates(
        self,
        *,
        html: str,
        base_url: str,
        host: str,
        out_dir: Path,
        artifacts: list[ProbeArtifact],
        signals: list[str],
        enabled: bool,
    ) -> ProbeFetchResult | None:
        if not enabled:
            return None
        for idx, candidate_url in enumerate(_json_candidate_urls(html, base_url), 1):
            allowed, robots_reason = self._check_robots(candidate_url)
            signals.append(f"json_candidate_{idx}_robots:{robots_reason}")
            if not allowed:
                continue
            resp = self._fetch(candidate_url, host)
            artifacts.append(
                self._write_artifact(
                    out_dir,
                    f"json-candidate-{idx}",
                    resp,
                    _extension_for(resp, fallback=".json"),
                )
            )
            if resp.status_code < 400 and resp.anti_bot_signal is None and _looks_like_json(resp):
                return resp
        return None

    def _write_artifact(
        self,
        out_dir: Path,
        name: str,
        resp: ProbeFetchResult,
        ext: str,
    ) -> ProbeArtifact:
        path = out_dir / f"{name}{ext}"
        path.write_bytes(resp.body)
        return ProbeArtifact(
            name=name,
            path=str(path),
            url=resp.final_url,
            status_code=resp.status_code,
            content_type=_content_type(resp),
            bytes_written=len(resp.body),
        )

    @staticmethod
    def _write_result(out_dir: Path, result: ProbeResult) -> None:
        (out_dir / "probe-result.json").write_text(result.to_json(), encoding="utf-8")


def probe_url(
    *,
    url: str,
    host: str,
    out_dir: Path,
    mode: ProbeMode = "auto",
) -> ProbeResult:
    client = HttpClient()

    def fetch(fetch_url: str, fetch_host: str) -> ProbeFetchResult:
        resp = client.fetch(fetch_url, host=fetch_host)
        return ProbeFetchResult(
            url=resp.url,
            final_url=resp.final_url,
            status_code=resp.status_code,
            headers=resp.headers,
            body=resp.body,
            error_kind=resp.error_kind,
            error_detail=resp.error_detail,
            anti_bot_signal=resp.anti_bot_signal,
        )

    def http_get(robots_url: str) -> tuple[int, bytes]:
        parsed = urlparse(robots_url)
        resp = client.fetch(robots_url, host=parsed.netloc, skip_anti_bot=True)
        return resp.status_code, resp.body

    robots = RobotsChecker(http_get)
    try:
        return SourceProbe(fetch=fetch, robots_allowed=robots.is_allowed).probe(
            url=url,
            host=host,
            out_dir=out_dir,
            mode=mode,
        )
    finally:
        client.close()


def _content_type(resp: ProbeFetchResult) -> str | None:
    return resp.headers.get("content-type") or resp.headers.get("Content-Type")


def _encoding(resp: ProbeFetchResult) -> str:
    content_type = _content_type(resp) or ""
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def _extension_for(resp: ProbeFetchResult, *, fallback: str) -> str:
    content_type = (_content_type(resp) or "").lower()
    if "json" in content_type:
        return ".json"
    if "html" in content_type:
        return ".html"
    return fallback


def _looks_like_json(resp: ProbeFetchResult) -> bool:
    content_type = (_content_type(resp) or "").lower()
    body = resp.body.lstrip()
    if "json" in content_type and body[:1] in (b"{", b"["):
        return True
    if body[:1] not in (b"{", b"["):
        return False
    try:
        json.loads(resp.body.decode(_encoding(resp), errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return True


def _detect_js_redirect(html: str, base_url: str) -> str | None:
    match = re.search(
        r"window\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return urljoin(base_url, match.group(1))


def _json_candidate_urls(html: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"""["']([^"']+\.json(?:\?[^"']*)?)["']""", html, re.IGNORECASE):
        href = match.group(1)
        if href.startswith(("data:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            candidates.append(absolute)
    return candidates


def _looks_like_js_shell(html: str) -> bool:
    lowered = html.lower()
    visible_text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.I | re.S)
    visible_text = re.sub(r"<[^>]+>", " ", visible_text)
    visible_text = re.sub(r"\s+", "", visible_text)
    script_count = len(re.findall(r"<script\b", lowered))
    has_app_root = bool(re.search(r"""<div[^>]+id=["'](?:app|root)["']""", lowered))
    has_bundle = bool(
        re.search(
            r"""<script[^>]+src=["'][^"']*(?:app|index|bundle|chunk)[^"']*\.js""",
            lowered,
        )
    )
    return (has_app_root and has_bundle and len(visible_text) < 80) or (
        script_count >= 3 and len(visible_text) < 120
    )
