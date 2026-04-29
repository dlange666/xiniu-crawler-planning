# Codegen Pipeline（每次 codegen 必加载）

> 适用对象：opencode / 其它 coding agent CLI。
> 调用方式：`opencode run -m <model> -f docs/codegen-pipeline.md -f .codegen-prompt.md`
> 本文件是 codegen 任务的 workflow-execution 模拟器：外部 agent 不会自动读取
> `skills/`，所以这里把分支、计划、任务、验收、PR、merge、notify 的执行顺序
> 写成硬约束。

---

## 0. 角色与边界

你是受限的 codegen Generator，本次任务只为**单个 host** 生成采集 adapter。

本 pipeline 模拟仓库主交付环路：

```
git-worktree -> plan -> task -> code -> gates -> eval -> PR -> merge -> notify-message
```

职责边界：

| 阶段 | 责任方 | 本次要求 |
|---|---|---|
| git-worktree | wrapper / 调用方 | 在独立 worktree + 合规分支运行 agent |
| plan | agent | 写本次 codegen plan，明确原子任务和验收门 |
| task | agent | 写 task 状态文件，推进 pending -> in_progress -> verifying -> completed/failed |
| code | agent | 只写允许范围内的 adapter / seed / test / golden |
| gates | wrapper + agent | agent 可自跑；wrapper 仍会重复跑确定性 gates |
| eval | agent | 写 green/red/partial 证据，判定以 gates/audit 为准 |
| PR | wrapper / 人 | gates green 后创建 draft PR；agent 不直接合并 |
| merge | 人审 / repo owner | PR 合并后进入 main；agent 不自合并 |
| notify-message | wrapper / 人 | 邮件/IM 尚未接入；只输出待发送消息草稿 |

## 1. 硬规则

- 不绕过验证码、登录认证、付费墙、technical challenge、robots 明示拒绝。
- 不使用 `captcha_solver`、`stealth`、`undetected_chromedriver`、`selenium-stealth`、`playwright-stealth` 等绕过保护工具。
- 不在 adapter 内发 HTTP 请求，不写 sleep / 限流 / retry；这些由 `infra/` 处理。
- 不 import 其它业务域；不修改已有 adapter。
- 不修改 `infra/`、`AGENTS.md`、`CLAUDE.md`、`pyproject.toml`。
- 任务 ID 必须是完整 `T-YYYYMMDD-NNN`，禁止写 `T-401` 这类简写。
- 如果任一 gate 或 audit 失败，eval 必须是 `red` 或 `partial`，禁止自判 green。

## 2. 允许写入范围

本次 codegen 允许新增或修改以下文件。除此之外默认禁止。

| 类别 | 路径 |
|---|---|
| Plan | `docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md` |
| Task | `docs/task/active/task-codegen-<host>-YYYY-MM-DD.json` |
| Eval | `docs/eval-test/codegen-<host>-YYYYMMDD.md` |
| Adapter | `domains/<business_context>/adapters/<host_slug>.py` |
| Seed | `domains/<business_context>/seeds/<host_slug>.yaml` |
| Golden HTML | `domains/<business_context>/golden/<host_slug>/*.html` |
| Golden JSON | `domains/<business_context>/golden/<host_slug>/*.golden.json` |
| Tests | `tests/<business_context>/test_adapter_<host_slug>.py` |

如确需触达其它路径，必须在 eval §5 写明原因并停下等待人审，不得自行扩大范围。

## 3. Adapter 契约

完整规则见 `docs/prod-spec/codegen-output-contract.md`。最小要求：

- 参考 `domains/gov_policy/adapters/ndrc.py` 的结构。
- `ADAPTER_META` 必须通过 `infra/adapter_registry/meta.py` 校验。
- `render_mode` 默认写 `direct`；发现 JS shell / 无限滚动 / challenge 时停下写 red，不升级到 headless。
- 必备 hook：

```python
def build_list_url(seed: SeedSpec, page: int) -> str: ...
def parse_list(html: str, url: str) -> ParseListResult: ...
def parse_detail(html: str, url: str) -> ParseDetailResult: ...
```

adapter 是纯函数：

- `parse_list` 抽 `detail_links` 和 `next_pages`。
- `parse_detail` 抽 `title`、`body_text`、`source_metadata`、`attachments`、`interpret_links`。
- helper 优先用 `infra/crawl/pagination_helpers.py`。
- `urljoin` 必须用，不手拼 URL。
- bs4 使用 `lxml` parser。

## 4. 执行阶段

### 4.1 git-worktree

wrapper 已在独立 worktree 中调用你。你必须先确认：

```bash
git status --short --branch
```

若不在 `agent/feature-YYYYMMDD-codegen-<host>` 形式的分支，eval 写 red 并停下。

### 4.2 plan

先写：

`docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md`

要求：

- 关联 spec：`docs/prod-spec/codegen-output-contract.md`
- 原子任务至少包括：站点探查、adapter/seed/golden/test、live smoke、audit、eval/PR handoff
- 每个任务 ID 用完整 `T-YYYYMMDD-NNN`
- 边界护栏写清：不 headless、不绕过反爬、不改 infra

### 4.3 task

再写：

`docs/task/active/task-codegen-<host>-YYYY-MM-DD.json`

要求：

- 和 plan 中任务 ID 一致
- 当前执行中的任务状态推进到 `in_progress`
- gates 跑完后改为 `verifying`
- PR 创建后才能标 `completed`；若 wrapper 尚未创建 PR，最多标 `verifying`

### 4.4 code

写 adapter / seed / golden / test：

- seed 必须含 `scope_mode`、`politeness_rps`、`max_pages_per_run`、`crawl_mode`、`entry_urls`。
- `politeness_rps` 不得高于默认 0.5。
- golden 至少 5 组 HTML+JSON；其中必须覆盖 1 个列表页和至少 1 个详情页。
- 测试至少覆盖 registry 校验、`parse_list` 发现详情、`parse_detail` 抽标题/正文/metadata。

### 4.5 gates

按顺序执行。前一项失败时可以停下写 eval；wrapper 可能为诊断继续跑其它 gate，
但最终任一 FAIL 都不能 green。

```bash
uv run pytest tests/ -q

uv run pytest tests/<business_context>/test_adapter_<host_slug>.py -v

uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('<business_context>', '<host>'))"

uv run python scripts/run_crawl_task.py \
  domains/<business_context>/seeds/<host_slug>.yaml \
  --max-pages 30 --max-depth 1 --scope-mode <scope_mode> --task-id <smoke_task_id>

uv run python scripts/audit_crawl_quality.py \
  --task-id <smoke_task_id> \
  --thresholds title_rate=0.95,body_500_rate=0.70,metadata_rate=0.30
```

green 条件：

| 检查 | 要求 |
|---|---|
| pytest | 既有 + 新增全绿 |
| registry | 能 resolve 当前 host |
| workflow docs | Plan / Task / Eval 三件套存在 |
| golden | HTML 与 `.golden.json` 各 >= 5 |
| live smoke | `raw_records_written >= 1` 且 `errors == 0` |
| audit | 退出码 0 |
| 合规 | 无 robots/challenge/captcha/auth/paywall 绕过行为 |

### 4.6 eval

写：

`docs/eval-test/codegen-<host>-YYYYMMDD.md`

必填：

- 判定：`green` / `red` / `partial`
- 复现命令：完整 gates 命令
- audit stdout：完整粘贴
- smoke 指标：raw_records、errors、anti_bot_events、host/cohort 分布
- 文件清单：本次新增/修改的 plan/task/code/golden/test
- PR handoff：若 green，写建议 PR 标题和 body；若 red，写下一轮动作
- notify-message 草稿：邮件/IM 尚未接入，只写一段可复制的消息

若本次任务来自 `crawl_task` / `crawl_task_execution`，wrapper 必须在 eval
落盘后同步任务表：

| 字段 | green | red / partial |
|---|---|---|
| `crawl_task_execution.status` | `completed` | `failed` |
| `last_run_status` | `green` | `red` 或 `partial` |
| `last_error_kind` | `NULL` | 见下方分类 |
| `last_error_detail` | `NULL` | 一句话说明失败原因、入口 URL、关键 gate |
| `last_eval_path` | 本次 eval 路径 | 本次 eval 路径 |
| `needs_manual_review` | `0` | 需人工改 PRD seed / scope / 合规策略时为 `1` |

`status` 只表示状态机位置，不要把具体站点问题扩成新状态。失败类型写
`last_error_kind`：

| error_kind | 适用场景 |
|---|---|
| `source_entry_unusable` | PRD/task 入口不可直接采集：入口命中 WAF、筛选页无可用详情、详情全部被 scope 拒绝 |
| `anti_bot` | challenge / captcha / WAF / auth 等保护措施命中 |
| `scope_mismatch` | 详情或分页在当前 scope 外，需改 `scope_mode` / allowlist / URL pattern |
| `render_required` | 静态抓取无法获得目标内容，需要 render/headless 或 API 能力 |
| `adapter_bug` | adapter 选择器、分页、URL 模式或解析逻辑错误 |
| `audit_gate_failed` | live smoke 有数据但质量门失败 |
| `infra_error` | DB、存储、网络基础设施或 wrapper 异常 |

失败模板：

```markdown
## 5. 异常案例

### 5.1 整体失败信号
- 失败步骤:
- last_error_kind:
- needs_manual_review:
- audit 输出:
- raw_records_written:
- errors / anti_bot_events:

### 5.2 根因分类
- [ ] 选择器假设错
- [ ] 站点是 JS 渲染
- [ ] 反爬命中
- [ ] 多 cohort DOM 异质性
- [ ] 业务正常但附件承载正文

### 5.3 下一步
```

### 4.7 PR

agent 不直接 merge。green 后只做 PR handoff：

- 建议标题：`feature(<host_slug>): add codegen adapter`
- body 包含：plan/task/eval 路径、gates 结果、audit 摘要、合规说明
- wrapper 或人审创建 draft PR

### 4.8 merge

merge 由 repo owner / reviewer 执行。agent 不执行 `gh pr merge`，不直接推 main。

### 4.9 notify-message

通知链路尚未接入。eval 最后一节写消息草稿即可：

```text
codegen <host> <green|red|partial>
PR: <pending or url>
Eval: docs/eval-test/codegen-<host>-YYYYMMDD.md
Key metrics: raw_records=<n>, errors=<n>, audit=<pass|fail>
Next: <review/merge/fix>
```

## 5. 与其它文档的关系

| 需要时读取 | 路径 |
|---|---|
| Adapter 完整契约 | `docs/prod-spec/codegen-output-contract.md` |
| ADAPTER_META 校验 | `infra/adapter_registry/meta.py` |
| 数据落库字段 | `docs/prod-spec/data-model.md` §4.2 |
| 业务字段标准 | `docs/prod-spec/domain-<business-context-kebab>.md` |
| 仓库总规则 | `AGENTS.md` |

不要主动扩大到 `docs/research/` 或无关业务域；token 用在目标 host 上。
