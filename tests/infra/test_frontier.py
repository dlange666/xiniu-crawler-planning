"""T-20260427-105 验收：30 URL 跨 3 host，验证 host 公平性。"""

from __future__ import annotations

from infra.frontier import Frontier, FrontierItem


def _mk_item(url: str, host: str, priority: float = 0.5) -> FrontierItem:
    return FrontierItem(
        url=url, url_fp=url, host=host, depth=0,
        parent_url_fp=None, discovery_source="seed",
        priority_score=priority,
    )


def test_submit_dedup() -> None:
    f = Frontier()
    assert f.submit(_mk_item("u1", "h1")) is True
    assert f.submit(_mk_item("u1", "h1")) is False  # 同 url_fp 拒收


def test_host_round_robin_fairness() -> None:
    """提交 30 URL 跨 3 host，next_ready 应轮转，前 3 次必定覆盖 3 host。"""
    f = Frontier()
    for i in range(10):
        f.submit(_mk_item(f"h1-{i}", "h1"))
        f.submit(_mk_item(f"h2-{i}", "h2"))
        f.submit(_mk_item(f"h3-{i}", "h3"))

    first_three = [f.next_ready() for _ in range(3)]
    hosts_seen = {it.host for it in first_three if it}
    assert hosts_seen == {"h1", "h2", "h3"}, f"got {hosts_seen}"


def test_max_pages_budget() -> None:
    f = Frontier(max_pages=5)
    for i in range(10):
        f.submit(_mk_item(f"u{i}", "h1"))
    dispatched = []
    while True:
        it = f.next_ready()
        if it is None:
            break
        dispatched.append(it)
    assert len(dispatched) == 5
    assert f.stats()["dispatched"] == 5


def test_empty_frontier_returns_none() -> None:
    f = Frontier()
    assert f.next_ready() is None


def test_stats_tracking() -> None:
    f = Frontier()
    f.submit(_mk_item("u1", "h1"))
    f.submit(_mk_item("u2", "h2"))
    s = f.stats()
    assert s["pending"] == 2
    assert s["active_hosts"] == 2
    assert s["dispatched"] == 0
    f.next_ready()
    s = f.stats()
    assert s["pending"] == 1
    assert s["dispatched"] == 1
