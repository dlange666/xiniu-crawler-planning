"""Adapter 注册中心专用异常。"""

from __future__ import annotations


class AdapterRegistryError(Exception):
    """所有 registry 异常的基类。"""


class InvalidAdapterMeta(AdapterRegistryError):
    """ADAPTER_META 字段缺失 / 类型错误 / pattern 编译失败。"""


class DuplicateAdapter(AdapterRegistryError):
    """同 (business_context, host) 注册了多次。"""


class AdapterNotFound(AdapterRegistryError):
    """get() 时未找到匹配的 adapter；异常消息包含可注册的候选列表。"""
