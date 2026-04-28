"""infra/crawl/strategies BFS/DFS 优先级公式。"""

from __future__ import annotations

from infra.crawl import compute_priority


def test_bfs_low_depth_higher_priority() -> None:
    p_d0 = compute_priority(depth=0, max_depth=2, base_score=0.5, strategy="bfs")
    p_d1 = compute_priority(depth=1, max_depth=2, base_score=0.5, strategy="bfs")
    p_d2 = compute_priority(depth=2, max_depth=2, base_score=0.5, strategy="bfs")
    assert p_d0 > p_d1 > p_d2


def test_dfs_high_depth_higher_priority() -> None:
    p_d0 = compute_priority(depth=0, max_depth=2, base_score=0.5, strategy="dfs")
    p_d1 = compute_priority(depth=1, max_depth=2, base_score=0.5, strategy="dfs")
    p_d2 = compute_priority(depth=2, max_depth=2, base_score=0.5, strategy="dfs")
    assert p_d2 > p_d1 > p_d0


def test_unknown_strategy_returns_base() -> None:
    p = compute_priority(depth=5, max_depth=10, base_score=0.7, strategy="unknown")
    assert p == 0.7


def test_base_score_distinguishes_within_depth() -> None:
    p_high = compute_priority(depth=1, max_depth=2, base_score=0.7, strategy="bfs")
    p_low = compute_priority(depth=1, max_depth=2, base_score=0.3, strategy="bfs")
    assert p_high > p_low
    # 但跨 depth 的差距应该远大于同 depth 内 base_score 差距
    p_d0 = compute_priority(depth=0, max_depth=2, base_score=0.3, strategy="bfs")
    assert p_d0 > p_high
