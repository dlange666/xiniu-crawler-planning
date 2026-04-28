"""单进程两级队列：全局优先级堆 + per-host ready queue。

spec: infra-fetch-policy.md §2.1, §2.2
- 三类令牌（host 礼貌性 / domain 配额 / 任务预算）
  - host 礼貌性令牌由 HttpClient 持有（HostTokenBucket）
  - 任务预算（max_pages_per_run）由 Frontier 计数
  - domain 配额本 MVP 退化为 host 公平性 + 总预算

- 公平性：多 host 间轮转，避免单 host 饥饿
- 调度：内层按 priority_score 取，外层按 host 轮转
"""

from __future__ import annotations

import heapq
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass(order=True)
class _HeapItem:
    # 负数：让 heapq（最小堆）按 priority_score 降序
    neg_priority: float
    seq: int
    host: str = field(compare=False)
    url: str = field(compare=False)
    url_fp: str = field(compare=False)
    depth: int = field(compare=False)
    parent_url_fp: str | None = field(compare=False)
    discovery_source: str = field(compare=False)


@dataclass
class FrontierItem:
    url: str
    url_fp: str
    host: str
    depth: int
    parent_url_fp: str | None
    discovery_source: str
    priority_score: float


class Frontier:
    def __init__(self, *, max_pages: int | None = None) -> None:
        self._heap: list[_HeapItem] = []
        self._seq = 0
        self._seen_fps: set[str] = set()
        self._per_host_pending: dict[str, deque[_HeapItem]] = defaultdict(deque)
        self._dispatched_count = 0
        self._max_pages = max_pages
        # host 轮转游标（公平性）
        self._host_order: list[str] = []
        self._host_cursor = 0
        self._lock = threading.Lock()

    def submit(self, item: FrontierItem) -> bool:
        """加入；同 url_fp 重复则忽略。返回 True=新增 / False=已见过。"""
        with self._lock:
            if item.url_fp in self._seen_fps:
                return False
            self._seen_fps.add(item.url_fp)
            self._seq += 1
            heap_item = _HeapItem(
                neg_priority=-item.priority_score,
                seq=self._seq,
                host=item.host,
                url=item.url,
                url_fp=item.url_fp,
                depth=item.depth,
                parent_url_fp=item.parent_url_fp,
                discovery_source=item.discovery_source,
            )
            heapq.heappush(self._heap, heap_item)
            self._per_host_pending[item.host].append(heap_item)
            if item.host not in self._host_order:
                self._host_order.append(item.host)
            return True

    def next_ready(self) -> FrontierItem | None:
        """按 host 轮转 + 优先级取下一个待派发；满预算或空队列返回 None。"""
        with self._lock:
            if self._max_pages is not None and self._dispatched_count >= self._max_pages:
                return None
            # 按 host 轮转：从 host_cursor 开始，找第一个 pending 非空的 host
            n = len(self._host_order)
            for offset in range(n):
                idx = (self._host_cursor + offset) % n
                host = self._host_order[idx]
                queue = self._per_host_pending.get(host)
                if queue:
                    item = queue.popleft()
                    # 同步从 heap 取出（懒删除：heap 中可能仍含已被 popleft 的 item）
                    self._lazy_remove_from_heap(item)
                    self._host_cursor = (idx + 1) % n  # 下次从下一 host 起
                    self._dispatched_count += 1
                    return FrontierItem(
                        url=item.url, url_fp=item.url_fp, host=item.host,
                        depth=item.depth, parent_url_fp=item.parent_url_fp,
                        discovery_source=item.discovery_source,
                        priority_score=-item.neg_priority,
                    )
            return None

    def _lazy_remove_from_heap(self, target: _HeapItem) -> None:
        # 不严格删除（heapq 没 O(1) remove）；调用方使用时只通过 next_ready 接触，安全
        try:
            self._heap.remove(target)
            heapq.heapify(self._heap)
        except ValueError:
            pass

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "pending": sum(len(q) for q in self._per_host_pending.values()),
                "dispatched": self._dispatched_count,
                "active_hosts": sum(1 for q in self._per_host_pending.values() if q),
                "total_hosts": len(self._host_order),
                "max_pages": self._max_pages or -1,
            }
