"""通用爬虫引擎（spec: docs/prod-spec/codegen-output-contract.md §2）。

业务无关：通过 adapter_resolver 注入站点适配器；通过 TaskSpec 参数化调度策略。

主要导出：
- CrawlEngine: 主引擎类
- RunReport: 端到端运行报告
- TaskSpec / SeedSpec: 任务与 seed 配置
- ParseListResult / ParseDetailResult: adapter hook 输出契约
- Attachment / SourceMetadata: 数据 payload
- compute_priority: BFS/DFS 优先级公式
- scope_allows: 作用域过滤
- compute_dedup_key: 解析层去重键
- load_seed: YAML → SeedSpec
"""

from .dedup import compute_dedup_key, is_duplicate, normalize_title
from .runner import CrawlEngine, RunReport
from .scope import scope_allows
from .seed_loader import load_seed
from .strategies import compute_priority
from .types import (
    Attachment,
    ParseDetailResult,
    ParseListResult,
    PolicyParsed,
    SeedSpec,
    SourceMetadata,
    TaskSpec,
)

__all__ = [
    "Attachment",
    "CrawlEngine",
    "ParseDetailResult",
    "ParseListResult",
    "PolicyParsed",
    "RunReport",
    "SeedSpec",
    "SourceMetadata",
    "TaskSpec",
    "compute_dedup_key",
    "compute_priority",
    "is_duplicate",
    "load_seed",
    "normalize_title",
    "scope_allows",
]
