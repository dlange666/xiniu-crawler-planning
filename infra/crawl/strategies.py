"""调度策略（BFS / DFS 优先级公式）。

spec: docs/research/research-ai-first-crawler-system-20260427.md §3-§4
     "层内近似 BFS + 全局优先级堆"
"""

from __future__ import annotations

DEPTH_WEIGHT = 100  # 每层 priority 阶差（远大于 base_score 的最大值 1.0）


def compute_priority(
    *,
    depth: int,
    max_depth: int = 1,
    base_score: float = 0.5,
    strategy: str = "bfs",
) -> float:
    """单 URL 调度优先级（高数值先出）。

    阶段实施版：仅 depth_weight + base_score。
    后续阶段可扩展 anchor / content_likelihood / parent_quality / aging（见 strategies 演进路线）。

    Args:
        depth: URL 当前层（0=seed，1=detail，...）
        max_depth: 任务允许的最大层（用于 BFS 计算反向权重）
        base_score: 基础分（默认 0.5）。adapter 可传入 anchor 启发式微调
        strategy: 'bfs' 优先低 depth；'dfs' 优先高 depth；其它返回 base_score 不区分层级

    Returns:
        priority 数值（高 = 先出）
    """
    if strategy == "bfs":
        depth_weight = (max_depth + 1 - depth) * DEPTH_WEIGHT
    elif strategy == "dfs":
        depth_weight = depth * DEPTH_WEIGHT
    else:
        depth_weight = 0.0
    return float(depth_weight) + float(base_score)
