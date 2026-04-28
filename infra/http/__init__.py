"""HTTP 客户端 infra（spec: docs/prod-spec/infra-fetch-policy.md §2.1, §3）。"""

from .anti_bot import detect_anti_bot
from .client import HttpClient, HttpResponse
from .token_bucket import HostTokenBucket

__all__ = ["HostTokenBucket", "HttpClient", "HttpResponse", "detect_anti_bot"]
