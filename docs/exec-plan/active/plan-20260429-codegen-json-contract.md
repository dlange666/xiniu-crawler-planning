# plan-20260429-codegen-json-contract

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-json-contract`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md` §3.1；`docs/codegen-pipeline.md` §4.3
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

降低 codegen agent 输出非标准 JSON 的概率，并让 wrapper 在无法修复时给出确定性
`red` 证据。具体针对 `docs/task/active/task-codegen-*.json`：wrapper 先生成
标准 `pr-task-file` 骨架，agent 只更新字段值；wrapper gate 再校验并规范化常见
markdown fence / 前后解释文本包裹场景。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-701 | [infra/codegen] Task JSON 标准输出与 wrapper 校验 | `codegen-output-contract.md` §3.1；`docs/codegen-pipeline.md` §4.3 | `scripts/run_codegen_for_adapter.py` 调 opencode 前写 task JSON 骨架；新增标准 JSON 校验、窄修复、`task_json` gate；更新 pipeline/spec 和单测 | `uv run pytest tests/infra/test_codegen_task_runner.py -q`、ruff、py_compile、全量 pytest | `verifying` |

## 4. 边界护栏

- 不改变 adapter 解析契约，不触碰业务域采集逻辑。
- 不把宽松 JSON 修复扩大成语义猜测；只抽取已存在的平衡 JSON object。
- 不跳过 red 记录：仍无法解析或缺必备字段时，`task_json` gate 必须失败并写 eval。
- 不接入新网络服务；仍使用本地 wrapper 与 opencode CLI。

## 5. 完成标准

`green` 仅当：

- T-20260429-701 在任务文件中标记 `completed`
- `codegen-output-contract.md` 已 bump rev 并记录修订历史
- task JSON 骨架、markdown 包裹修复、非法 JSON 拒绝均有单测
- 定向测试、ruff、py_compile、全量 pytest 通过
- 评估证据写入 `docs/eval-test/`
