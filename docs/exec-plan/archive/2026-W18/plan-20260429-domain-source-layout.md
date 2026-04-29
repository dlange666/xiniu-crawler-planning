# plan-20260429-domain-source-layout

## 1. 元信息

- **Plan ID**：`plan-20260429-domain-source-layout`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md`、`docs/prod-spec/domain-gov-policy.md`
- **状态**：`completed`
- **负责角色**：`Planner`

## 2. 目标

把旧的 `domains/<context>/adapters`、`seeds`、`golden` 横向目录迁移为按
source 聚合的目录结构，确保手写 adapter、codegen 产物、registry、测试和
active spec 使用同一命名规则。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-801 | [domains/gov_policy] source 聚合目录迁移 | `codegen-output-contract.md` §2；`domain-gov-policy.md` §8 | 迁移 NDRC adapter/seed/golden 到 `domains/gov_policy/ndrc/`；registry 扫描 `domains/<context>/<source>/<source>_adapter.py`；codegen wrapper 只写新路径；同步 active spec、计划与测试命名 | `pytest` 针对 registry/codegen/NDRC；全量 `pytest tests/ -q`；`ruff`；`py_compile`；`git diff --check` | `completed` |

## 4. 边界护栏

- 不迁移历史 research 原稿中的旧示例；active spec 与 active plan 作为执行权威。
- 不改业务解析逻辑，只改路径、发现规则和引用。
- 不删除旧路径兼容扫描，迁移期允许 registry 读取 `domains/<context>/adapters/*.py`。

## 5. 完成标准

`green` 仅当：

- NDRC 已按 source 目录聚合，旧横向目录无 tracked 文件残留。
- codegen wrapper 与 adapter registry 默认使用新路径。
- active spec / architecture / active plan 不再把旧路径作为当前契约。
- 评估证据写入 `docs/eval-test/domain-source-layout-20260429.md`。
