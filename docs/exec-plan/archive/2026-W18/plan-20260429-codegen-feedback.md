# Plan: codegen feedback loop

## 1. 元信息

- **Plan ID**：`plan-20260429-codegen-feedback`
- **关联规格**：`docs/prod-spec/codegen-output-contract.md`
- **状态**：`completed`
- **负责角色**：`Planner / Generator / Evaluator`
- **关联 PR**：https://github.com/dlange666/xiniu-crawler-planning/pull/21

## 2. 目标

把最近 source codegen 暴露的问题固化为平台能力：wrapper red 后自动回灌失败证据并让 opencode 自主迭代；golden 从纯数量门槛改为覆盖型配对门槛；audit 增加脚本污染质量信号；prompt 明确 SourceMetadata、业务 scope、分页 fallback 和 infra 边界。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-901 | [codegen/wrapper] red feedback 自动迭代 | `codegen-output-contract.md` §3.1, §5.3 | `run_codegen_for_adapter.py` 支持 wrapper red 后生成 `.codegen-feedback.md`，回灌失败 gate 输出并最多迭代 3 次 | 单测覆盖 feedback prompt；ruff / py_compile / pytest | `completed` |
| T-20260429-902 | [codegen/golden] 覆盖型配对 golden gate | `codegen-output-contract.md` §3, §5.1 | golden gate 校验 ≥1 list、≥3 detail；有分页信号时 ≥1 pagination/list_2；要求 HTML/JSON 同名配对 | 单测覆盖通过样本与缺分页样本 | `completed` |
| T-20260429-903 | [audit/quality] 文本污染与 URL scope 质量门 | `codegen-output-contract.md` §3.1, §5.2 | audit 增加 `script_noise_rate`，wrapper 增加 `detail_url_pattern` live-smoke 入库 URL 匹配 gate | 单测覆盖 script noise；wrapper gate py_compile | `completed` |
| T-20260429-904 | [prompt/spec] 收口提示词与契约同步 | `codegen-output-contract.md` §6.2 | 更新 pipeline、per-task prompt、spec revision：SourceMetadata、short body sample、scope、pagination fallback、infra 边界 | 文档 diff review；spec rev bump | `completed` |
| T-20260429-905 | [eval] 记录本次验证证据 | `docs/eval-test/template.md` | 写入 `docs/eval-test/codegen-feedback-loop-20260429.md` | eval 判定 green | `completed` |

## 4. 边界护栏

- 不修改具体 source adapter。
- 不在 codegen 任务中允许 agent 修改 `infra/`；infra 能力提升仍必须走独立 infra 任务。
- 不降低 audit 阈值；失败样本必须用于修复解析或 scope。
- 不引入 headless、stealth、验证码绕过、登录绕过能力。

## 5. 完成标准

`green` 仅当：

- `scripts/run_codegen_for_adapter.py`、`scripts/audit_crawl_quality.py`、相关单测通过 ruff
- 局部与全量 pytest 通过
- `codegen-output-contract.md` 已 bump revision 并追加修订历史
- 本计划对应任务文件和 eval 证据齐全
