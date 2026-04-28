"""T-20260427-104 验收：RFC 9309 五种典型情形。"""

from __future__ import annotations

from infra.robots import RobotsChecker

ALLOW_ALL = b"User-agent: *\nAllow: /\n"
DENY_ALL = b"User-agent: *\nDisallow: /\n"
DENY_ADMIN = b"User-agent: *\nDisallow: /admin/\nAllow: /\n"


def _mock_get(status: int, body: bytes = b""):
    def fn(url: str) -> tuple[int, bytes]:
        return status, body
    return fn


def test_robots_200_parsed_allowed() -> None:
    rc = RobotsChecker(_mock_get(200, ALLOW_ALL))
    allowed, _ = rc.is_allowed("https://x.com/foo")
    assert allowed is True


def test_robots_200_parsed_disallowed() -> None:
    rc = RobotsChecker(_mock_get(200, DENY_ADMIN))
    assert rc.is_allowed("https://x.com/admin/secret")[0] is False
    assert rc.is_allowed("https://x.com/public/file")[0] is True


def test_robots_404_treated_as_allow_all() -> None:
    rc = RobotsChecker(_mock_get(404))
    allowed, reason = rc.is_allowed("https://x.com/anything")
    assert allowed is True
    assert "status=404" in reason


def test_robots_5xx_complete_disallow() -> None:
    rc = RobotsChecker(_mock_get(503))
    allowed, reason = rc.is_allowed("https://x.com/anything")
    assert allowed is False
    assert "complete disallow" in reason


def test_robots_network_error_disallow() -> None:
    def boom(url: str):  # noqa: ARG001
        raise OSError("connection refused")
    rc = RobotsChecker(boom)
    allowed, reason = rc.is_allowed("https://x.com/anything")
    assert allowed is False
    assert "complete disallow" in reason


def test_robots_cache_hit() -> None:
    calls = {"n": 0}
    def fn(url: str) -> tuple[int, bytes]:
        calls["n"] += 1
        return 200, ALLOW_ALL
    rc = RobotsChecker(fn)
    rc.is_allowed("https://x.com/a")
    rc.is_allowed("https://x.com/b")
    rc.is_allowed("https://x.com/c")
    # 同一 origin 仅取一次 robots
    assert calls["n"] == 1
