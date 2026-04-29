"""Per-host RPS 令牌桶。

spec: docs/prod-spec/infra-fetch-policy.md §2.1 三层令牌 - host 礼貌性。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    rps: float
    burst: int
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.monotonic)


def _new_bucket(rps: float, burst: int) -> _Bucket:
    """新桶起步默认装满 burst，首请求即时通过。"""
    return _Bucket(rps=rps, burst=burst, tokens=float(burst))


class HostTokenBucket:
    """Per-host token bucket。线程安全。

    take(host) 阻塞直到拿到令牌；遵守该 host 的 RPS 与 burst 容量。
    新建桶起步装满 burst，首次请求不被令牌限制（避免冷启动等待）。
    """

    def __init__(self, default_rps: float = 1.0, default_burst: int = 2) -> None:
        self.default_rps = default_rps
        self.default_burst = default_burst
        self._buckets: dict[str, _Bucket] = {}
        self._cooldown_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def configure(self, host: str, *, rps: float, burst: int) -> None:
        """设定特定 host 的 RPS（业务域 seeds 注入）。

        守门：业务域只能用更保守值（rps 不大于 default_rps）。
        """
        if rps > self.default_rps:
            rps = self.default_rps
        with self._lock:
            self._buckets[host] = _new_bucket(rps, burst)

    def cooldown(self, host: str, seconds: float) -> None:
        """对 host 设 cooldown（如 Retry-After 或反爬命中）。"""
        with self._lock:
            self._cooldown_until[host] = max(
                self._cooldown_until.get(host, 0.0),
                time.monotonic() + seconds,
            )

    def take(self, host: str) -> float:
        """阻塞直到取到一个令牌；返回实际等待时长（秒）。"""
        start = time.monotonic()
        while True:
            with self._lock:
                # cooldown 优先
                cd = self._cooldown_until.get(host, 0.0)
                now = time.monotonic()
                if cd > now:
                    wait = cd - now
                else:
                    bucket = self._buckets.get(host)
                    if bucket is None:
                        bucket = _new_bucket(self.default_rps, self.default_burst)
                        self._buckets[host] = bucket
                    elapsed = now - bucket.last_refill
                    bucket.tokens = min(
                        bucket.burst,
                        bucket.tokens + elapsed * bucket.rps,
                    )
                    bucket.last_refill = now
                    if bucket.tokens >= 1.0:
                        bucket.tokens -= 1.0
                        return time.monotonic() - start
                    wait = (1.0 - bucket.tokens) / bucket.rps
            time.sleep(min(wait, 0.5))
