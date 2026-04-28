"""Frontier（spec: docs/prod-spec/infra-fetch-policy.md §2.1, §2.2）。

单进程内嵌：全局优先级堆 + per-host ready queue。
MVP 不持久化（重启即清空）；持久 checkpoint 是 TD-010 暂缓。
"""

from .queue import Frontier, FrontierItem

__all__ = ["Frontier", "FrontierItem"]
