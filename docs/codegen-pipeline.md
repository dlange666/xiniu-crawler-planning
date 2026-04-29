# Codegen Pipeline（每次 codegen 必加载）

> 适用对象：opencode / 其它 coding agent CLI。
> 调用方式：`opencode run -m <model> -f docs/codegen-pipeline.md -f .codegen-prompt.md`
> 本文件只写 agent 必须遵守的硬约束；具体 task 参数和复现命令由 `.codegen-prompt.md`
> 注入，最终判定由 wrapper gates 决定。

## 0. 角色与边界

你是受限的 codegen Generator，本次只为**单个 host** 生成采集 adapter。

流程：

```text
git-worktree -> plan -> task -> code -> gates -> eval -> PR handoff
```

职责：

| 阶段 | 责任方 | 要求 |
|---|---|---|
| worktree | wrapper | 独立 worktree + 合规分支 |
| plan/task/code/eval | agent | 写允许范围内的交付物 |
| gates | wrapper + agent | agent 自跑；wrapper 复跑并拥有最终判定 |
| red feedback | wrapper + agent | wrapper 回灌失败证据；agent 最多自主修复 3 轮 |
| publish | wrapper | green 自动提交并推送完整 codegen 分支；red 只提交并推送 eval 诊断报告 |
| PR/merge | wrapper / 人 | agent 只写 handoff，不创建或合并 PR |

## 1. 硬规则

- 不绕过验证码、登录、付费墙、technical challenge、robots 明示拒绝。
- 不使用 `captcha_solver`、`stealth`、`undetected_chromedriver`、`selenium-stealth`、`playwright-stealth` 等绕过库。
- adapter hook 必须是纯函数：不联网、不 sleep、不限流、不 retry；这些由 `infra/` 处理。
- 探查必须使用 `scripts/probe_source.py`，artifact 只能写在 `runtime/probe/<host_slug>/`。
- 所有写入必须在当前 worktree 且落入 §2 允许范围；禁止写 `/tmp`、父目录、其它 worktree。
- 不 import 其它业务域；不修改已有 adapter；不修改 `infra/`、`AGENTS.md`、`CLAUDE.md`、`pyproject.toml`。
- 任务 ID 必须是完整 `T-YYYYMMDD-NNN`。
- 任一 gate/audit 失败时，eval 必须是 `red` 或 `partial`；禁止自判 green。
- 未跑 live smoke + audit 禁止 green；只凭单测/registry 通过禁止 green。
- Task 文件必须是标准 JSON，禁止 markdown fence、注释、尾逗号和 JSON 外文本。
- wrapper 会追加 `Wrapper Gate Result`；red 时会生成 `.codegen-feedback.md`，agent 必须基于真实失败证据继续修复，禁止降低阈值。
- wrapper 拥有提交边界：green 分支提交 plan/task/eval/adapter/seed/golden fixture/test；red 分支只提交 eval 诊断报告，避免半成品 adapter 进入分支历史。

## 2. 允许写入范围

| 类别 | 路径 |
|---|---|
| Plan | `docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md` |
| Task | `docs/task/active/task-codegen-<host>-YYYY-MM-DD.json` |
| Eval | `docs/eval-test/codegen-<host>-YYYYMMDD.md` |
| Adapter | `domains/<business_context>/<host_slug>/<host_slug>_adapter.py` |
| Seed | `domains/<business_context>/<host_slug>/<host_slug>_seed.yaml` |
| Golden fixture | `tests/domains/<business_context>/<host_slug>/fixtures/<host_slug>_golden_*` |
| Tests | `tests/domains/<business_context>/<host_slug>/test_adapter.py` |

如确需触达其它路径，必须在 eval 写明原因并停下等待人审。

`host_slug` 必须承载源站主体职责，不得使用 `www`、`wap`、`m`、`mobile` 等通用渠道前缀。
示例：`www.most.gov.cn -> most`、`wap.miit.gov.cn -> miit`、`search.sh.gov.cn -> sh_search`。

## 3. Adapter 契约

参考 `docs/prod-spec/codegen-output-contract.md` 与 `domains/gov_policy/ndrc/ndrc_adapter.py`。

必备：

- `ADAPTER_META` 通过 `infra/adapter_registry/meta.py` 校验。
- hook：`build_list_url(seed, page)`、`parse_list(html, url)`、`parse_detail(html, url)`。
- `parse_list` 返回业务 scope 内的 `detail_links` 和自然页码排序的 `next_pages`。
- `parse_detail` 返回 `title`、干净 `body_text`、`SourceMetadata(raw={...})`、`attachments`、`interpret_links`。
- 测试读取 metadata 必须用 `result.source_metadata.raw`。
- `body_text` 不得夹带 `var ... =`、`function`、`document.`、`window.`、`<script`、`</script`、`$(...)` 等 JS/CSS/DOM 噪声。
- `detail_links` 必须过滤导航、搜索、社媒、移动入口、栏目页等非业务链接。
- URL 解析使用 `urljoin`；BeautifulSoup 使用 `lxml`。

能力选择：

- 先跑 probe。`robots_disallow` / `blocked` / `fetch_failed` 直接 red，不绕过。
- 优先级：`json_api -> static_html/SSR -> headless_required`。
- 发现 JS shell 时，先查公开静态 JS、CDN JSON、XHR/fetch/API、feed/sitemap、SSR 入口；只有都不可用才 red 为 `render_required`。
- 分页/API/字段 helper 优先用 `infra/` 现有能力；helper 不覆盖但页面有稳定静态信号时，在当前 source adapter 内写 host-bounded fallback。fallback 必须纯函数、有测试和 golden，且 eval 记录是否建议另开 infra 任务提升。

## 4. 交付物要求

### 4.1 Plan

写 `docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md`：

- 关联 `docs/prod-spec/codegen-output-contract.md`
- 原子任务覆盖探查、adapter、seed、golden、test、live smoke、audit、eval handoff
- 任务 ID 使用完整 `T-YYYYMMDD-NNN`
- 护栏写清：不 headless、不绕过保护、不改 infra

### 4.2 Task

wrapper 已预生成 `docs/task/active/task-codegen-<host>-YYYY-MM-DD.json`：

- 保留 `schema_version`、`file_kind=pr-task-file`、`status_enum`、`branch`、`date`
- gates 跑完后最多标 `verifying`；PR 创建后才可标 `completed`
- 每次编辑后执行 `uv run python -m json.tool <task-json>`

### 4.3 Code

- seed 必须含 `scope_mode`、`politeness_rps`、`max_pages_per_run`、`crawl_mode`、`entry_urls`。
- 无明确站点限制时 `politeness_rps=1.0`，不得高于默认 1.0。
- golden 使用覆盖型配对门槛：至少 1 个 list、3 个 detail；若有分页信号，至少 1 个 pagination/list_2。
- HTML 与 `.golden.json` 必须同名一一配对，例如 `<host>_golden_detail_1.html` 对应 `<host>_golden_detail_1.golden.json`。
- `.golden.json` 必须由当前 adapter 输出重新生成并通过 `json.tool`，聚合 JSON 不能替代配对样本。
- 测试至少覆盖 registry、`parse_list` 详情链接、`parse_detail` 标题/正文/metadata；有分页信号时断言 `next_pages`。

## 5. Gates 与判定

agent 必须执行 `.codegen-prompt.md` 给出的完整 gates；wrapper 会复跑。

green 条件：

| Gate | 要求 |
|---|---|
| pytest | 既有 + 新增全绿 |
| registry | 能 resolve 当前 host |
| workflow docs | Plan / Task / Eval 三件套存在 |
| task_json | 标准 JSON 且满足 `pr-task-file` 必备字段 |
| golden | 覆盖型配对样本通过 |
| live_smoke | `raw_records_written >= 1` 且 `errors == 0` |
| audit | 退出码 0；默认含 `title_rate`、`body_100_rate`、`metadata_rate`、`script_noise_rate_max` |
| detail_url_pattern | live smoke 入库 URL 至少 95% 匹配 `ADAPTER_META.detail_url_pattern` |
| 合规 | 无 robots/challenge/captcha/auth/paywall 绕过 |

任一失败即 red/partial。red 前必须排查并记录：

1. 删除 `runtime/db/dev.db*` 后重跑 live smoke。
2. `curl` seed URL，记录 HTTP 状态、content-type、响应体是否含目标列表数据。
3. 单独调用 `parse_list(seed_response, seed_url)`，确认 `detail_links`。
4. `curl` 一个详情 URL 并调用 `parse_detail`，确认 title/body/metadata。
5. 分析 audit short body samples、script noise samples、detail URL pattern miss；优先修 scope 和 parser，不降 gate。
6. parser 可用但 runner 无数据时，检查 seed、scope、robots、checkpoint、`ADAPTER_META.list_url_pattern`。

## 6. Eval

写 `docs/eval-test/codegen-<host>-YYYYMMDD.md`：

- 判定：`green` / `red` / `partial`
- 复现命令和 audit stdout
- smoke 指标：raw_records、errors、anti_bot_events、host/cohort 分布
- source capability：probe verdict、API/SSR/headless 选择依据、infra helper/fallback 记录
- 文件清单：plan/task/code/golden/test/eval
- PR handoff：green 写建议标题/body；red 写下一轮最小动作
- notify-message 草稿

wrapper 会追加最终 gate 表、失败项、opencode exit code、日志路径和 worktree 路径。

来自 `crawl_task` / `crawl_task_execution` 的任务，wrapper 会同步：

| 字段 | green | red / partial |
|---|---|---|
| `status` | `completed` | `failed` |
| `last_run_status` | `green` | `red` / `partial` |
| `last_error_kind` | `NULL` | 失败分类 |
| `last_error_detail` | `NULL` | 失败 gate + 关键观测 |
| `last_eval_path` | 本次 eval | 本次 eval |
| `needs_manual_review` | `0` | 需人工改 seed/scope/合规策略时为 `1` |

建议 `last_error_kind`：`source_entry_unusable`、`anti_bot`、`scope_mismatch`、
`render_required`、`adapter_bug`、`audit_gate_failed`、`infra_error`。
