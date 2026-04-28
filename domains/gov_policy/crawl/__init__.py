"""通用采集编排器（runner）。

使用 infra/http + infra/frontier + infra/robots，按 adapter 列表/详情解析与落库。
"""

from .runner import CrawlRunner, RunReport

__all__ = ["CrawlRunner", "RunReport"]
