"""HTTP 客户端（spec: docs/prod-spec/infra-fetch-policy.md §2, §3, §5）。

实现：
- 真实身份 UA（不伪装浏览器）
- per-host token bucket（§2.1）
- 重试矩阵 + 退避公式（§3.2）：min(cap, base*2^attempt) + jitter
- Retry-After 优先（§3.3）
- 反爬识别（§5）→ 命中即返回，不重试
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

from .anti_bot import detect_anti_bot
from .token_bucket import HostTokenBucket

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "xiniu-crawler/0.1 "
    "(+https://xiniudata.com/crawler-info; mailto:crawler-ops@xiniudata.com)"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass
class HttpResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int
    attempts: int
    final_url: str  # 跟随重定向后
    error_kind: str | None = None     # network/parse/anti_bot_*/...
    error_detail: str | None = None
    anti_bot_signal: str | None = None  # auth_required / rate_limited / waf_block / ...


class HttpClient:
    def __init__(
        self,
        *,
        token_bucket: HostTokenBucket | None = None,
        timeout_sec: float = 30.0,
        retry_max: int = 3,
        backoff_base_sec: float = 1.0,
        backoff_cap_sec: float = 60.0,
        cooldown_on_challenge_sec: float = 600.0,
    ) -> None:
        self.token_bucket = token_bucket or HostTokenBucket()
        self.timeout = httpx.Timeout(timeout_sec)
        self.retry_max = retry_max
        self.backoff_base_sec = backoff_base_sec
        self.backoff_cap_sec = backoff_cap_sec
        self.cooldown_on_challenge_sec = cooldown_on_challenge_sec
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=self.timeout,
            http2=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        """解析 Retry-After header；接受秒数或 HTTP-date。"""
        if not value:
            return None
        v = value.strip()
        if v.isdigit():
            return float(v)
        try:
            dt = parsedate_to_datetime(v)
            if dt is None:
                return None
            return max(0.0, (dt.timestamp() - time.time()))
        except Exception:  # noqa: BLE001
            return None

    def _compute_backoff(self, attempt: int) -> float:
        backoff = min(
            self.backoff_cap_sec,
            self.backoff_base_sec * (2 ** attempt),
        )
        jitter = random.uniform(0, 0.5 * backoff)
        return backoff + jitter

    def fetch(
        self,
        url: str,
        *,
        host: str,
        if_none_match: str | None = None,
        if_modified_since: str | None = None,
        skip_anti_bot: bool = False,
    ) -> HttpResponse:
        """同步抓一个 URL。返回 HttpResponse；不抛异常。

        skip_anti_bot=True 时跳过反爬识别（专供 robots.txt 等基础设施请求使用）：
        spec infra-fetch-policy.md §4 robots 4xx → 全允许、5xx → complete disallow
        是 RobotsChecker 的责任，不应通过 HttpClient 触发 host cooldown。
        """
        headers: dict[str, str] = {}
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        if if_modified_since:
            headers["If-Modified-Since"] = if_modified_since

        attempt = 0
        last_error_kind: str | None = None
        last_error_detail: str | None = None
        start = time.monotonic()
        last_status: int | None = None
        last_resp_headers: dict[str, str] = {}
        last_body: bytes = b""
        last_final_url: str = url

        while attempt <= self.retry_max:
            self.token_bucket.take(host)
            try:
                resp = self._client.get(url, headers=headers)
            except httpx.TimeoutException as e:
                last_error_kind = "timeout"
                last_error_detail = str(e)
                logger.warning("fetch timeout host=%s url=%s attempt=%d", host, url, attempt)
            except (httpx.NetworkError, httpx.RemoteProtocolError) as e:
                last_error_kind = "network"
                last_error_detail = f"{type(e).__name__}: {e}"
                logger.warning("fetch network err host=%s url=%s attempt=%d %s",
                               host, url, attempt, e)
            except httpx.HTTPError as e:
                last_error_kind = "http_error"
                last_error_detail = f"{type(e).__name__}: {e}"
                logger.warning("fetch http_error host=%s url=%s attempt=%d %s",
                               host, url, attempt, e)
            else:
                # 成功收到响应
                last_status = resp.status_code
                last_resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                last_body = resp.content
                last_final_url = str(resp.url)

                # 反爬识别（status / cookies / body）
                anti_bot = None if skip_anti_bot else detect_anti_bot(
                    status_code=resp.status_code,
                    headers=last_resp_headers,
                    body=last_body,
                )
                if anti_bot:
                    self.token_bucket.cooldown(host, self.cooldown_on_challenge_sec)
                    return HttpResponse(
                        url=url, status_code=resp.status_code,
                        headers=last_resp_headers, body=last_body,
                        elapsed_ms=int((time.monotonic() - start) * 1000),
                        attempts=attempt + 1, final_url=last_final_url,
                        error_kind=f"anti_bot_{anti_bot}",
                        error_detail=anti_bot,
                        anti_bot_signal=anti_bot,
                    )

                # 304 / 200/3xx：直接返回成功
                if resp.status_code < 400:
                    return HttpResponse(
                        url=url, status_code=resp.status_code,
                        headers=last_resp_headers, body=last_body,
                        elapsed_ms=int((time.monotonic() - start) * 1000),
                        attempts=attempt + 1, final_url=last_final_url,
                    )

                # 4xx 非 429（401/403 已被 anti_bot 兜住）→ 不重试
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    last_error_kind = f"http_{resp.status_code}"
                    last_error_detail = resp.reason_phrase
                    break  # 不重试

                # 429 / 5xx：进入退避
                last_error_kind = f"http_{resp.status_code}"
                last_error_detail = resp.reason_phrase

                if resp.status_code == 429:
                    retry_after = self._parse_retry_after(last_resp_headers.get("retry-after"))
                    if retry_after is not None:
                        # Retry-After 优先；同时设置 host cooldown
                        self.token_bucket.cooldown(host, retry_after)
                        time.sleep(retry_after)
                        attempt += 1
                        continue

            # 退避
            if attempt >= self.retry_max:
                break
            sleep_for = self._compute_backoff(attempt)
            time.sleep(sleep_for)
            attempt += 1

        return HttpResponse(
            url=url, status_code=last_status or 0,
            headers=last_resp_headers, body=last_body,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            attempts=attempt + 1, final_url=last_final_url,
            error_kind=last_error_kind,
            error_detail=last_error_detail,
        )
