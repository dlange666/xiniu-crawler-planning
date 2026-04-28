"""解析层严格去重（spec: architecture.md §3 + data-model.md §4.2.3）。

联合键：(policy_title_norm, pub_code, content_sha256) 一致才去重；
不一致全部保留。simhash64 仅作信号写入 policy_similar_cluster 表（MVP 暂缓）。
"""

from .strict import compute_dedup_key, is_duplicate, normalize_title

__all__ = ["compute_dedup_key", "is_duplicate", "normalize_title"]
