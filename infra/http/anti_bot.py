"""反爬识别信号（spec: infra-fetch-policy.md §5）。

仅识别，不绕过。命中 → host cooldown / disable / 人工审核。
"""

from __future__ import annotations

import re

# 标题关键词（命中即视作 challenge）
_CHALLENGE_TITLE_PATTERNS = (
    re.compile(r"just a moment", re.IGNORECASE),
    re.compile(r"verify you are human", re.IGNORECASE),
    re.compile(r"访问频率限制"),
    re.compile(r"系统繁忙"),
    re.compile(r"请输入验证码"),
    re.compile(r"403\s*Forbidden", re.IGNORECASE),
)

# WAF / Cloudflare cookie 标记
_WAF_COOKIE_MARKERS = ("cf_chl_", "__cf_bm", "_csrf_token_for_waf")

# DOM 中的 captcha / challenge iframe 特征
_CHALLENGE_DOM_PATTERNS = (
    re.compile(r'<iframe[^>]+src="[^"]*challenge[^"]*"', re.IGNORECASE),
    re.compile(r'<form[^>]+action="[^"]*captcha[^"]*"', re.IGNORECASE),
    re.compile(r"recaptcha", re.IGNORECASE),
    re.compile(r"hcaptcha", re.IGNORECASE),
)


def detect_anti_bot(
    *,
    status_code: int,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> str | None:
    """检测反爬信号；命中返回信号名，未命中返回 None。

    返回值（信号名，与 anti_bot_events.signal 字段语义一致）：
      - "auth_required"   : 401
      - "waf_block"       : 403 或 Set-Cookie 含 WAF marker
      - "challenge_page"  : 标题/DOM 含 challenge 特征
      - "captcha"         : DOM 含 captcha/recaptcha/hcaptcha
      - None              : 未命中

    注：429 (rate_limited) 不在反爬识别范畴；它是限流信号，由 HttpClient 的
    Retry-After 重试逻辑处理（见 infra-fetch-policy.md §3.1 重试矩阵）。
    """
    headers = headers or {}

    if status_code == 401:
        return "auth_required"

    # WAF / Cloudflare cookie marker
    set_cookie = headers.get("set-cookie", "") + headers.get("Set-Cookie", "")
    if any(m in set_cookie for m in _WAF_COOKIE_MARKERS):
        return "waf_block"

    if status_code == 403:
        return "waf_block"

    if body:
        try:
            text = body.decode("utf-8", errors="ignore")[:8192]  # 只看前 8KB
        except Exception:  # noqa: BLE001
            return None
        for pat in _CHALLENGE_TITLE_PATTERNS:
            if pat.search(text):
                return "challenge_page"
        for pat in _CHALLENGE_DOM_PATTERNS:
            if pat.search(text):
                return "captcha" if "captcha" in pat.pattern.lower() else "challenge_page"

    return None
