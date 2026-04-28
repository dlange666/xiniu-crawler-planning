"""RFC 9309 robots.txt 检查（spec: infra-fetch-policy.md §4）。

状态码语义（关键）：
- 200 + 可解析  → 按规则执行
- 4xx           → 视作"无 robots，全允许"
- 5xx / 网络错误 → **视作 complete disallow**（host 24h 冷却）
- 解析失败      → 同 5xx

缓存 TTL: 24h。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

CACHE_TTL_SEC = 86400  # 24h


@dataclass
class _Entry:
    parser: RobotFileParser | None  # None = complete disallow
    fetched_at: float
    fetch_status: int  # 200 / 4xx / 5xx / -1（network error）


class RobotsChecker:
    """同步、线程不安全（MVP 单进程足够）。"""

    def __init__(self, http_get: callable, *, cache_ttl_sec: int = CACHE_TTL_SEC) -> None:
        """http_get(url) -> (status_code, body: bytes) 注入；不直接依赖 HttpClient 避免循环。"""
        self._http_get = http_get
        self._cache: dict[str, _Entry] = {}
        self._cache_ttl_sec = cache_ttl_sec

    def _origin(self, url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    def _load(self, origin: str) -> _Entry:
        robots_url = f"{origin}/robots.txt"
        try:
            status, body = self._http_get(robots_url)
        except Exception as e:  # noqa: BLE001
            logger.warning("robots fetch network error origin=%s err=%s", origin, e)
            return _Entry(parser=None, fetched_at=time.monotonic(), fetch_status=-1)

        if status == 200:
            parser = RobotFileParser()
            try:
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
                return _Entry(parser=parser, fetched_at=time.monotonic(), fetch_status=200)
            except Exception as e:  # noqa: BLE001
                logger.warning("robots parse error origin=%s err=%s", origin, e)
                return _Entry(parser=None, fetched_at=time.monotonic(), fetch_status=500)

        if 400 <= status < 500:
            # 4xx → 全允许（per RFC 9309 + spec §4）
            parser = RobotFileParser()
            parser.parse([])
            return _Entry(parser=parser, fetched_at=time.monotonic(), fetch_status=status)

        # 5xx 或其他 → complete disallow
        return _Entry(parser=None, fetched_at=time.monotonic(), fetch_status=status)

    def is_allowed(self, url: str, user_agent: str = "*") -> tuple[bool, str]:
        """返回 (allowed, reason)；reason 含 status / 决策原因，便于日志诊断。"""
        origin = self._origin(url)
        now = time.monotonic()
        entry = self._cache.get(origin)
        if entry is None or (now - entry.fetched_at) > self._cache_ttl_sec:
            entry = self._load(origin)
            self._cache[origin] = entry

        if entry.parser is None:
            return False, f"status={entry.fetch_status} → complete disallow"

        allowed = entry.parser.can_fetch(user_agent, url)
        return allowed, f"status={entry.fetch_status} parser-decided"

    def clear_cache(self) -> None:
        self._cache.clear()
