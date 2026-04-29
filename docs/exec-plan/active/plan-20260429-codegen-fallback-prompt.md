# plan-20260429-codegen-fallback-prompt

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-fallback-prompt`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md`、`docs/prod-spec/infra-crawl-engine.md`
- **状态**：`active`
- **负责角色**：`Planner / Generator / Evaluator`

## 2. 目标

让 codegen agent 在 infra helper 未覆盖但页面静态信号明确时，仍能在当前 domain source 内自主完成 bounded fallback；同时把已确认通用的 `createPageHTML(container_id,total,cur,prefix,suffix,rows)` 变体提升到 infra pagination helper。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-801 | [codegen/prompt] 明确 domain fallback 边界 | `codegen-output-contract.md` §3.1；`docs/codegen-pipeline.md` §3-§4 | 更新 pipeline 与 wrapper per-task prompt：helper 不覆盖时 agent 在当前 source adapter/test/golden 内写 fallback，禁止 codegen 任务修改 infra | review prompt diff；`uv run ruff check scripts/run_codegen_for_adapter.py` | `completed` |
| T-20260429-802 | [infra/crawl] 支持 createPageHTML 变体 | `infra-crawl-engine.md` §6 | 扩展 `parse_create_page_html`，兼容单引号 total-first 与 container-id-first 变体 | `uv run pytest tests/infra/test_pagination_helpers.py -q`；`uv run pytest tests/ -q` | `completed` |
| T-20260429-803 | [eval] 记录验收证据 | `docs/eval-test/template.md` | 写入 eval-test 记录测试结果与边界结论 | eval 判定 green | `completed` |

## 4. 边界护栏

- 本计划不改既有 source adapter；CSRC adapter 的临时 fallback 可在后续 rebase 后删除。
- codegen agent 仍禁止修改 `infra/`；通用能力提升必须走单独 infra 任务。
- 不引入 headless/render 能力，不改变 robots / 限流策略。

## 5. 完成标准

`green` 仅当：

- `parse_create_page_html` 兼容旧 total-first 与新 container-id-first 变体。
- codegen prompt 明确 domain fallback 边界，且保留不改 infra 的限制。
- 相关单元测试与全量测试通过。
- 评估证据写入 `docs/eval-test/`。
