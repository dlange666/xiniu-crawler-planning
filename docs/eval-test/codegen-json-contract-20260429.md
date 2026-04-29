# Codegen JSON Contract 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-json-contract` / `T-20260429-701`
> **验证 spec**：`codegen-output-contract.md` §3.1；`docs/codegen-pipeline.md` §4.3
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本次验证回答：codegen agent 输出 task JSON 时，如果出现 markdown fence 或解释文本
包裹，wrapper 是否能自动规范化；如果仍不是标准 JSON，是否会明确 red。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | agent 自行从零写 task JSON，wrapper 只检查文件是否存在 |
| Candidate（候选） | wrapper 预生成标准 JSON 骨架，并增加 `task_json` gate |
| 数据切片 | `scripts/run_codegen_for_adapter.py` 的 task JSON 产物路径 |
| 评估口径 | 标准骨架、包裹文本修复、非法 JSON 拒绝、全量回归 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | pytest `tmp_path` |

## 3. 复现命令

```bash
uv run pytest tests/infra/test_codegen_task_runner.py -q

uv run ruff check scripts/run_codegen_for_adapter.py tests/infra/test_codegen_task_runner.py

uv run python -m py_compile scripts/run_codegen_for_adapter.py

uv run pytest tests/ -q

git diff --check
```

## 3.1 关联 PR

- Draft PR: https://github.com/dlange666/xiniu-crawler-planning/pull/13

## 4. 度量结果

| Gate | 结果 |
|---|---|
| codegen task runner 单测 | `green`：12 passed |
| ruff | `green`：All checks passed |
| py_compile | `green`：exit 0 |
| 全量测试 | `green`：95 passed |
| diff whitespace | `green`：无输出 |

## 5. 覆盖点

| 场景 | 断言 |
|---|---|
| wrapper 预生成 | 生成标准 `pr-task-file` JSON，并包含完整任务 ID |
| markdown 包裹 | 从 fence / 前后解释文本中抽取平衡 JSON object 并规范化 |
| 前置大括号噪声 | 跳过非 JSON 的 `{...}` 片段，继续扫描后续合法 task JSON |
| 非标准 JSON | 不猜测修复尾逗号等语义错误，返回 gate failure |
| wrapper gates | `run_gates` 增加 `task_json` 结果 |
| adapter 命名 | `wap.miit.gov.cn -> miit`，避免 `wap.py` 这类通用渠道名 |
| audit 默认门 | 默认正文长度门使用 `body_100_rate`，`body_500_rate` 降为观测指标 |
| domain source layout | codegen 产物路径使用 `domains/<context>/<source>/<source>_*`，registry 发现新路径并兼容旧 adapter 目录 |

## 6. 结论与决策

- **判定**：`green`
- **理由**：标准骨架、包裹文本规范化、非法 JSON 拒绝和 wrapper gate 均有测试覆盖；全量回归通过。
- **风险**：窄修复只处理 JSON object 被包裹的情况；缺逗号、尾逗号、注释等仍要求 agent 或人工修复，避免误改语义。
- **阻塞项**：无。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 关闭哪些 task / plan | `T-20260429-701` completed；`plan-20260429-codegen-json-contract` archived |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：codegen task JSON 标准输出与 wrapper gate 验收记录 |
