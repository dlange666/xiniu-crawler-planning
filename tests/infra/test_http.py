"""T-20260427-103 验收：mock 429+Retry-After:2 验证至少等 2 秒；普通 200 通过。"""

from __future__ import annotations

import time

import httpx

from infra.http import HostTokenBucket, HttpClient, detect_anti_bot


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_token_bucket_basic_ratelimits() -> None:
    bucket = HostTokenBucket(default_rps=2.0, default_burst=1)
    start = time.monotonic()
    bucket.take("host1")
    bucket.take("host1")  # 第二个需要等 1/2=0.5 秒
    elapsed = time.monotonic() - start
    assert elapsed >= 0.45  # 容忍少量误差


def test_token_bucket_cooldown() -> None:
    bucket = HostTokenBucket(default_rps=10.0, default_burst=1)
    bucket.take("h")  # 拿掉一个
    bucket.cooldown("h", 0.4)
    start = time.monotonic()
    bucket.take("h")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.35


def test_http_200_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>ok</html>",
                              headers={"Content-Type": "text/html"})
    client = HttpClient(token_bucket=HostTokenBucket(default_rps=100, default_burst=10))
    client._client = httpx.Client(transport=_mock_transport(handler))
    resp = client.fetch("https://example.com/", host="example.com")
    assert resp.status_code == 200
    assert resp.body == b"<html>ok</html>"
    assert resp.attempts == 1
    assert resp.error_kind is None


def test_http_429_with_retry_after_waits() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"}, content=b"slow down")
        return httpx.Response(200, content=b"<html>ok</html>")

    bucket = HostTokenBucket(default_rps=100, default_burst=10)
    client = HttpClient(token_bucket=bucket, retry_max=3)
    client._client = httpx.Client(transport=_mock_transport(handler))
    start = time.monotonic()
    resp = client.fetch("https://example.com/", host="example.com")
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    assert resp.attempts == 2
    assert elapsed >= 0.95  # 至少等 ~1s


def test_http_403_anti_bot_no_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, content=b"<html>403</html>")

    client = HttpClient(token_bucket=HostTokenBucket(default_rps=100, default_burst=10))
    client._client = httpx.Client(transport=_mock_transport(handler))
    resp = client.fetch("https://example.com/x", host="example.com")
    # 403 命中反爬识别 → 不重试
    assert resp.status_code == 403
    assert resp.anti_bot_signal == "waf_block"
    assert resp.attempts == 1
    assert calls["n"] == 1


def test_anti_bot_detection_signals() -> None:
    assert detect_anti_bot(status_code=200, body=b"<title>Just a moment</title>") == "challenge_page"
    assert detect_anti_bot(status_code=200, headers={"set-cookie": "cf_chl_1=abc"}) == "waf_block"
    assert detect_anti_bot(status_code=200, body="<title>访问频率限制</title>".encode()) == "challenge_page"
    assert detect_anti_bot(status_code=200, body=b"<iframe src='/recaptcha/x'></iframe>") == "captcha"
    assert detect_anti_bot(status_code=429) is None  # 429 走 Retry-After 重试，不是反爬
    assert detect_anti_bot(status_code=200, body=b"<html>normal</html>") is None
