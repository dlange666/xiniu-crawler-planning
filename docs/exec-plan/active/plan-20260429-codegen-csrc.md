# Plan: codegen-csrc - 为 www.csrc.gov.cn 生成采集适配器

> **关联 spec**: `docs/prod-spec/codegen-output-contract.md`
> **创建日期**: 2026-04-29
> **状态**: active

## 目标

为 `www.csrc.gov.cn` (中国证券监督管理委员会) 实现采集适配器，采集政策文件（规章）。

## 原子任务

| ID | 任务 | 状态 | 验收门 |
|---|---|---|---|
| T-20260429-701 | 站点探查与入口确认 | completed | probe verdict = static_html |
| T-20260429-702 | 实现 adapter (csrc_adapter.py) | completed | parse_list/parse_detail 正确 |
| T-20260429-703 | 创建 seed (csrc_seed.yaml) | completed | 含 scope_mode: same_origin |
| T-20260429-704 | 生成 golden (HTML + .golden.json) | completed | >= 5 组 |
| T-20260429-705 | 编写测试 (test_csrc_adapter.py) | completed | registry 校验 + 核心解析 |
| T-20260429-706 | Live smoke + audit | completed | raw_records >= 1, audit pass |
| T-20260429-707 | Eval + PR handoff | completed | eval 文档 + PR 建议 |

## 边界护栏

- 不使用 headless render
- 不绕过反爬（robots/验证码/challenge）
- 不修改 infra/AGENTS.md/pyproject.toml
- 入口 URL: `http://www.csrc.gov.cn/csrc/c106256/fg.shtml` (规章列表)

## 站点分析

| 项目 | 值 |
|---|---|
| 入口 URL | `http://www.csrc.gov.cn/csrc/c106256/fg.shtml` |
| render_mode | direct (static HTML, SSR) |
| 列表结构 | table > tbody > tr > td.info > a.list |
| 详情 URL 模式 | `/csrc/c106256/c<id>/content.shtml` |
| 分页 | createPageHTML('page_div', 5, 1, 'fg', 'shtml', 89) - 共 5 页 / 89 条 |
| 反爬状态 | robots status=200, anti_bot_detected=false |

## 修订历史

| rev | 日期 | 摘要 |
|---|---|---|
| 1 | 2026-04-29 | 初始化 plan |
