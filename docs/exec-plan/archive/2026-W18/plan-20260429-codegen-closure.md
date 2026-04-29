# plan-20260429-codegen-closure

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-closure`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md` rev 12；`docs/codegen-pipeline.md` §4.5
- **状态**：`completed`
- **负责角色**：`Planner`

## 2. 目标

把 NFRA codegen retry 暴露出的收口问题固化为 agent 必读协议：实现完成后必须跑完整
gates，live smoke 前清理本地 smoke DB，red 前必须排查 seed、parser、scope、robots、
checkpoint 和可替代的 JSON/CDN/API 入口。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-901 | [infra/codegen] 强化 agent 收口与 red 前排查协议 | `codegen-output-contract.md` rev 12；`docs/codegen-pipeline.md` §4.5 | 更新 pipeline 硬规则、wrapper per-task prompt、spec 修订历史；单测断言 prompt 包含 smoke DB 清理、audit DB、red 前 parser/scope/checkpoint 排查 | `uv run pytest tests/infra/test_codegen_task_runner.py -q`、`uv run pytest tests/ -q`、ruff、py_compile、diff check | `completed` |

## 4. 边界护栏

- 不改 adapter 契约，不改变 crawl runner 行为。
- 不把提示词替代 wrapper gates；最终 green/red 仍由 wrapper 确定性 gates 覆盖。
- 不要求 agent 修改 `infra/` 来适配单站点；优先引导其穷尽 direct JSON/CDN/API/SSR 路径。

## 5. 完成标准

- `docs/codegen-pipeline.md` 明确收口协议和 red 前排查。
- `scripts/run_codegen_for_adapter.py` 生成的 `.codegen-prompt.md` 带具体 host 的收口命令。
- `codegen-output-contract.md` bump rev 并记录修订历史。
- 单测和全量回归通过。
