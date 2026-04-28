# Plan: codegen-most (www.most.gov.cn)

> **版本**：rev 1 · **最近修订**：2026-04-28 · **状态**：verifying

## 关联 spec

- `docs/prod-spec/codegen-output-contract.md`（Adapter 契约）
- `docs/codegen-pipeline.md`（codegen 工作流）
- `docs/prod-spec/domain-gov-policy.md`（业务字段标准）
- `docs/prod-spec/data-model.md`（数据落库字段）

## 目标

使用 `codegen-pipeline` 为 `www.most.gov.cn`（科技部）生成并验收一个
`gov_policy` 单 host 政策采集 adapter。站点经静态 HTML smoke 确认可直连解析，
本任务不启用 headless。

| 项 | 值 |
|---|---|
| business_context | gov_policy |
| host | www.most.gov.cn |
| entry URL | https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/ |
| scope_mode | same_origin |
| render_mode | direct |
| smoke task_id | 2026042841 |

## 原子任务

| ID | 任务 | 验收门 | 状态 |
|---|---|---|---|
| T-20260428-501 | 站点探查：fetch 列表页，分析详情 URL 模式 | 列表页 HTML 存 golden；主政策路径识别为 `flfg/bmgz/gfxwj` | completed |
| T-20260428-502 | 站点探查：fetch 详情页，分析字段 DOM 结构 | 详情页 HTML 存 golden；metadata table 与 `#Zoom` 正文结构确认 | completed |
| T-20260428-503 | 实现 adapter：`most.py`（`build_list_url` / `parse_list` / `parse_detail`） | `ADAPTER_META` 通过 registry 校验；metadata 抽取无越界 | completed |
| T-20260428-504 | 实现 seed：`most.yaml`（含 `scope_mode: same_origin`） | YAML 语法正确；RPS 不高于 0.5 | completed |
| T-20260428-505 | 创建 golden：≥5 组 HTML + `.golden.json` | 1 个列表页 + 5 个详情页，HTML/JSON 配对 | completed |
| T-20260428-506 | 实现 test：`test_adapter_most.py` | MOST 专项测试 10/10 通过 | completed |
| T-20260428-507 | Live smoke：`run_crawl_task.py --max-pages 30` | `raw_records_written=14`，`errors=0`，`anti_bot_events=0` | completed |
| T-20260428-508 | Audit：`audit_crawl_quality.py` | `title_rate=100%`，`body_500_rate=85.7%`，`metadata_rate=100%` | completed |
| T-20260428-509 | 写 eval 与 PR handoff | `docs/eval-test/codegen-most-20260428.md` 记录 green 证据；PR 待创建 | verifying |

## 边界护栏

- **不 headless**：`render_mode=direct`，未触发 JS shell / challenge 信号。
- **不绕过反爬**：未使用任何验证码、登录、付费墙或技术 challenge 绕过工具；robots.txt 返回 404，按未声明拒绝处理。
- **不改 infra**：本任务只新增 `gov_policy` adapter、seed、golden、测试与 workflow 文档。
- **不跨域**：详情、相关文档和附件均在 `www.most.gov.cn` 作用域下处理；列表采集只收主政策路径，排除 `zcjd` 解读列表作为主详情。

## 验收摘要

| Gate | 结果 |
|---|---|
| `uv run pytest tests/gov_policy/test_adapter_most.py -q` | pass：10 passed |
| live smoke | pass：14 raw records，0 errors |
| audit | pass：quality audit verdict PASS |

最终完整 gates 见 `docs/eval-test/codegen-most-20260428.md`。
