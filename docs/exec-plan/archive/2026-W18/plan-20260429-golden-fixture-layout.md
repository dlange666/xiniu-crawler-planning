# plan-20260429-golden-fixture-layout

## 1. 元信息

- **Plan ID**：`plan-20260429-golden-fixture-layout`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md`；`docs/prod-spec/domain-gov-policy.md`；`docs/prod-spec/codegen-auto-merge.md`
- **状态**：`completed`
- **负责角色**：`Planner / Generator / Evaluator`

## 2. 目标

把 source golden HTML/JSON 从 `domains/` 运行时代码目录迁移到 tests 的
domain/source 镜像目录，明确 golden 是版本化测试夹具；同时提取 codegen
与 pytest 共用的 golden 配对/覆盖校验逻辑，避免在脚本和单测里重复维护路径
与校验规则。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-1101 | [tests/codegen] golden fixture 目录收口与契约复用 | `codegen-output-contract.md` §2-§5；`domain-gov-policy.md` §8；`codegen-auto-merge.md` §3 | 将 `domains/gov_policy/<source>/*_golden_*` 移至 `tests/domains/gov_policy/<source>/fixtures/`；将 adapter 测试迁移为 `tests/domains/gov_policy/<source>/test_adapter.py`；新增 `infra/adapter_contract/golden.py` 供 pytest 与 codegen wrapper 复用；同步 docs/codegen-pipeline 与相关 spec revision | `uv run pytest tests/domains/gov_policy tests/infra/test_codegen_task_runner.py tests/infra/test_adapter_contract.py -q`；`uv run pytest -q`；`uv run ruff check .`；`git diff --check`；eval 判定 green | `completed` |

## 4. 边界护栏

- 不修改任何 source adapter 的解析业务规则。
- 不把 golden fixture 放回 `domains/` 或 `runtime/`。
- 不把测试夹具逻辑接入 crawler 运行主路径；`infra/adapter_contract/` 仅用于离线契约验证。
- 不改动真实抓取限速、robots、反爬处理逻辑。

## 5. 完成标准

`green` 仅当：

- T-20260429-1101 对应任务文件、spec 修订与 eval 证据齐全。
- `domains/gov_policy/<source>/` 下不再包含 `*_golden_*` 文件。
- 所有 source 的 adapter 测试位于 `tests/domains/gov_policy/<source>/test_adapter.py`。
- codegen wrapper 的 golden gate 读取 `tests/domains/<context>/<source>/fixtures/`。
- 针对性与全量测试、ruff、diff check 通过。
