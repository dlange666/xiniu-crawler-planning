"""Codegen wrapper：编排 opencode 跑单 host adapter codegen。

注意：本模块是 wrapper 自身代码，不在 codegen agent 的"infra 禁区"内。
agent 的"不修改 infra/" 规则指 infra/adapter_registry/、infra/crawl/、
infra/storage/ 等 capability 模块；agent 不会触达本目录。
"""
