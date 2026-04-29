# Codegen Fallback Prompt + createPageHTML Helper Eval

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-fallback-prompt` / `T-20260429-801` / `T-20260429-802` / `T-20260429-803`
> **验证 spec**：`validates: codegen-output-contract.md §3.1, infra-crawl-engine.md §6`
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

CSRC codegen 试跑暴露出两个问题：opencode 在 infra pagination helper 返回空时没有主动写 domain fallback，且 `createPageHTML('page_div',5,1,'fg','shtml',89)` 这类政府站常见变体未被通用 helper 覆盖。本评估验证本次改造是否同时收紧 agent 边界并补齐 infra 通用能力。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | `parse_create_page_html` 只覆盖 total-first 双引号形式；codegen prompt 未明确 domain fallback 边界 |
| Candidate（候选） | helper 覆盖 total-first 单/双引号与 container-id-first 变体；prompt 要求 helper 不覆盖时在当前 source adapter 内 fallback 且禁止 codegen 修改 infra |
| 数据切片 | synthetic createPageHTML 样本；全量 pytest 回归 |
| 评估口径 | helper 解析结果、prompt 边界、单元测试、全量测试 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | 无 |

## 3. 度量结果 · 聚合

| 指标 | Control | Candidate | Δ | 备注 |
|---|---|---|---|---|
| total-first 双引号 | pass | pass | 0 | 保持兼容 |
| total-first 单引号 | fail | pass | +1 case | `createPageHTML(3,1,'index','shtml')` |
| container-id-first | fail | pass | +1 case | `createPageHTML('page_div',5,1,'fg','shtml',89)` |
| codegen fallback 边界 | 未明确 | 明确 | +1 guard | fallback 只能写 domain source，禁止 codegen 改 infra |

## 4. 复现命令

```bash
uv run pytest tests/infra/test_pagination_helpers.py -q
uv run pytest tests/ -q
uv run ruff check infra/crawl/pagination_helpers.py scripts/run_codegen_for_adapter.py tests/infra/test_pagination_helpers.py
uv run python -m json.tool docs/task/active/task-codegen-fallback-prompt-2026-04-29.json
```

## 5. 异常案例

无。

## 6. 结论与决策

- **判定**：`green`
- **理由**：helper 覆盖新增分页变体，prompt 明确 opencode 只能在 domain source 内实现 fallback；本分支作为独立 infra 任务补通用能力。
- **风险**：更多 createPageHTML 变体仍可能存在；后续由站点试跑继续补充 infra helper。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 是否开新 task | 否 |
| 是否开 fix-task | 否 |
| 关闭哪些 task / plan | PR 创建后关闭 `T-20260429-801` / `T-20260429-802` / `T-20260429-803` |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版 |
