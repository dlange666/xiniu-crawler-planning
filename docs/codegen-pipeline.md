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
| task | wrapper + agent | wrapper 预生成标准 JSON 骨架；agent 只更新字段值，推进 pending -> in_progress -> verifying -> completed/failed |
| code | agent | 只写允许范围内的 adapter / seed / test / golden |
| gates | wrapper + agent | agent 可自跑；wrapper 仍会重复跑确定性 gates |
| eval | agent + wrapper | agent 写 green/red/partial 证据；wrapper 在 gates 后强制创建或追加最终 gate 记录，判定以 gates/audit 为准；red 时 wrapper 最多回灌 3 次失败证据让 agent 自主修复 |
| PR | wrapper / 人 | gates green 后创建 draft PR；agent 不直接合并 |
| merge | 人审 / repo owner | PR 合并后进入 main；agent 不自合并 |
| notify-message | wrapper / 人 | 邮件/IM 尚未接入；只输出待发送消息草稿 |

## 1. 硬规则

- 不绕过验证码、登录认证、付费墙、technical challenge、robots 明示拒绝。
- 不使用 `captcha_solver`、`stealth`、`undetected_chromedriver`、`selenium-stealth`、`playwright-stealth` 等绕过保护工具。
- 不在 adapter 内发 HTTP 请求，不写 sleep / 限流 / retry；这些由 `infra/` 处理。
- 站点探查必须通过 `scripts/probe_source.py`，artifact 只能写在 repo 内
  `runtime/probe/<host_slug>/`；不得把样本写到 `/tmp` 后再读取。
- 所有写入必须落在当前 worktree 内，且只能写 §2 允许范围；禁止使用
  `/tmp/*`、父目录、其它 worktree 或任何绝对路径作为产物目标。
- 不 import 其它业务域；不修改已有 adapter。
- 不修改 `infra/`、`AGENTS.md`、`CLAUDE.md`、`pyproject.toml`。
- 任务 ID 必须是完整 `T-YYYYMMDD-NNN`，禁止写 `T-401` 这类简写。
- 如果任一 gate 或 audit 失败，eval 必须是 `red` 或 `partial`，禁止自判 green。
- 禁止在未跑 live smoke + audit 时写 green；禁止只凭单测或 registry 通过写 green。
- Task 文件必须是标准 JSON：禁止 markdown fence、注释、尾逗号、JSON 外解释文本；
  每次编辑后必须执行 `uv run python -m json.tool <task-json>`。
- wrapper 会在 gates 后向 `docs/eval-test/codegen-<host>-YYYYMMDD.md`
  创建或追加 `Wrapper Gate Result`；即使 opencode 异常退出或漏写 eval，
  red 结果也必须留下 eval-test 证据。
- wrapper gate red 时会生成 `.codegen-feedback.md`，回灌失败 gate、pytest 输出、
  audit 样本和 URL pattern miss；agent 必须基于该文件继续迭代，不得降低阈值或
  把非业务链接误入归咎于 gate。

## 2. 允许写入范围

本次 codegen 允许新增或修改以下文件。除此之外默认禁止。

| 类别 | 路径 |
|---|---|
| Plan | `docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md` |
| Task | `docs/task/active/task-codegen-<host>-YYYY-MM-DD.json` |
| Eval | `docs/eval-test/codegen-<host>-YYYYMMDD.md` |
| Adapter | `domains/<business_context>/<host_slug>/<host_slug>_adapter.py` |
| Seed | `domains/<business_context>/<host_slug>/<host_slug>_seed.yaml` |
| Golden HTML | `domains/<business_context>/<host_slug>/<host_slug>_golden_*.html` |
| Golden JSON | `domains/<business_context>/<host_slug>/<host_slug>_golden_*.golden.json` |
| Tests | `tests/<business_context>/test_<host_slug>_adapter.py` |

如确需触达其它路径，必须在 eval §5 写明原因并停下等待人审，不得自行扩大范围。

`host_slug` 必须承载源站主体职责，不得使用 `www`、`wap`、`m`、`mobile`
等通用渠道前缀作为目录或文件名。示例：`www.most.gov.cn -> most`、
`wap.miit.gov.cn -> miit`、`search.sh.gov.cn -> sh_search`。

## 3. Adapter 契约

完整规则见 `docs/prod-spec/codegen-output-contract.md`。最小要求：

- 参考 `domains/gov_policy/ndrc/ndrc_adapter.py` 的结构。
- `ADAPTER_META` 必须通过 `infra/adapter_registry/meta.py` 校验。
- `render_mode` 默认写 `direct`。发现 JS shell / Angular / Vue / React 时，不得直接写
  `render_required`；必须先查静态 JS、CDN JSON、XHR/fetch/API、feed/sitemap、
  SSR 入口。只有公开 direct 采集路径全部不可用时，才允许 red 为 `render_required`。
- 探查必须使用 `scripts/probe_source.py --mode auto` 的 verdict。发现稳定、
  robots 允许、可回放的公开 JSON/API artifact 时，采集优先级为：
  `json_api -> static_html/SSR -> headless_required`；未发现 API 时才用
  direct HTML，`headless_required` 只写 red 等待 render-pool。
- 必备 hook：

```python
def build_list_url(seed: SeedSpec, page: int) -> str: ...
def parse_list(html: str, url: str) -> ParseListResult: ...
def parse_detail(html: str, url: str) -> ParseDetailResult: ...
```

adapter 是纯函数：

- `parse_list` 抽 `detail_links` 和 `next_pages`。
- `parse_detail` 抽 `title`、`body_text`、`source_metadata`、`attachments`、`interpret_links`。
- `source_metadata` 必须是 `SourceMetadata(raw={...})`；测试读取时使用
  `result.source_metadata.raw`，不得把它当普通 dict。
- `body_text` 不得夹带 JS/CSS/DOM 脚本噪声，例如 `var ... =`、`function`、
  `document.`、`window.`、`<script`、`</script`、`$(...)`。若正文来自 JS
  模板字面量，只抽正文变量自身，不能从第一个反引号截到最后一个反引号。
- `detail_links` 必须属于本任务业务 scope；短正文 audit sample、社媒/移动入口/
  搜索页/导航页等非业务链接必须在 `parse_list` 或 `ADAPTER_META.detail_url_pattern`
  过滤。
- `next_pages` 必须按自然页码排序。
- helper 优先用 `infra/crawl/pagination_helpers.py`。
- 当 `infra/` helper 返回空，但页面存在明确、稳定、可静态解析的分页/API/字段信号时，
  **不得直接放弃或写 red**。agent 必须先在当前 adapter 内实现有界 fallback：
  - fallback 只允许写在 `domains/<business_context>/<host_slug>/` 的当前 source
    adapter/test/golden 中；codegen 任务不得修改 `infra/`。
  - fallback 只能是纯函数解析或 URL 生成逻辑，不能联网、sleep、retry 或绕过保护。
  - fallback 只能依赖当前 host 的静态样本、公开 URL 规律与 `urljoin`。
  - fallback 必须有单元测试和 golden 期望覆盖。
  - eval 必须记录：哪个 infra helper 未覆盖、fallback 规则、是否建议另开 infra 任务提升。
  - 只有公开 direct/API/SSR 路径和有界 fallback 都不可用时，才允许 red。
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

wrapper 已预先写入：

`docs/task/active/task-codegen-<host>-YYYY-MM-DD.json`

要求：

- 保留 wrapper 生成的 `schema_version`、`file_kind=pr-task-file`、`status_enum`、
  `branch`、`date` 等结构字段
- 和 plan 中任务 ID 一致；如新增任务记录，ID 必须是完整 `T-YYYYMMDD-NNN`
- 当前执行中的任务状态推进到 `in_progress`
- gates 跑完后改为 `verifying`
- PR 创建后才能标 `completed`；若 wrapper 尚未创建 PR，最多标 `verifying`
- 文件必须能通过：

```bash
uv run python -m json.tool docs/task/active/task-codegen-<host>-YYYY-MM-DD.json
```

### 4.4 code

写 adapter / seed / golden / test：

- 先执行：

```bash
uv run python scripts/probe_source.py \
  --url <entry_url> \
  --host <host> \
  --mode auto \
  --out runtime/probe/<host_slug>/
```

- 必须读取 `runtime/probe/<host_slug>/probe-result.json`。
- 若 verdict 为 `robots_disallow` / `blocked` / `fetch_failed`，停下写 red eval。
- 若 verdict 为 `headless_required`，停下写 red eval，说明后续需要 render-pool。
- 若 verdict 为 `json_api`，优先基于 JSON artifact 设计列表解析；该优先级高于
  static HTML / SSR / headless；仍不得在 hook 内联网。
- 若 verdict 为 `static_html`，使用 direct HTML / SSR 输出实现 adapter。
- 如果列表页含分页信号（例如 `createPageHTML`、`page=N`、`index_N.html`、
  `下一页`、`data-page`、公开 JS 中的 page config），必须先用
  `infra/crawl/pagination_helpers.py`。helper 不能识别时，必须在 adapter 内写
  host-bounded fallback 并用测试证明 `parse_list(...).next_pages` 非空；不得把
  "infra helper 未覆盖"当作 source 不可采或 render_required；不得在 codegen
  任务中修改 `infra/`。
- 如果列表页或公开 JS 含 API / JSON / CDN 数据 URL 信号，但 probe 没自动归类为
  `json_api`，必须人工检查 artifact 中的 URL 与响应结构；能稳定回放时优先按
  JSON/API 设计，不能稳定回放时在 eval 写明证据。
- seed 必须含 `scope_mode`、`politeness_rps`、`max_pages_per_run`、`crawl_mode`、`entry_urls`。
- `politeness_rps` 不得高于默认 1.0；无明确站点限制时使用 1.0。
- golden 采用覆盖门槛而非纯数量门槛：至少 1 个列表页配对、3 个详情页配对；
  若存在分页信号，至少再提供 1 个分页页配对。HTML 与 `.golden.json` 必须一一
  同名配对，例如 `<host>_golden_detail_1.html` 对应
  `<host>_golden_detail_1.golden.json`；聚合型 JSON 不能替代配对样本。
- 测试至少覆盖 registry 校验、`parse_list` 发现详情、`parse_detail` 抽标题/正文/metadata。
  若存在分页信号，测试还必须断言 `next_pages` 中至少 1 个预期分页 URL。

### 4.5 gates

按顺序执行。实现或修复完成后必须完整执行本节，不能在代码写完后直接结束。
wrapper 也会重复执行这些确定性 gates；最终任一 FAIL 都不能 green。

```bash
uv run pytest tests/ -q

uv run pytest tests/<business_context>/test_<host_slug>_adapter.py -v

uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('<business_context>', '<host>'))"

uv run python -m json.tool docs/task/active/task-codegen-<host_slug>-YYYY-MM-DD.json

uv run python - <<'PY'
from scripts.run_codegen_for_adapter import golden_artifacts_exist
import argparse
from pathlib import Path
args = argparse.Namespace(host='<host>', business_context='<business_context>')
raise SystemExit(0 if golden_artifacts_exist(Path('.'), args) else 1)
PY

rm -f runtime/db/dev.db runtime/db/dev.db-wal runtime/db/dev.db-shm

uv run python scripts/run_crawl_task.py \
  domains/<business_context>/<host_slug>/<host_slug>_seed.yaml \
  --max-pages 30 --max-depth 1 --scope-mode <scope_mode> --task-id <smoke_task_id>

uv run python scripts/audit_crawl_quality.py \
  --task-id <smoke_task_id> \
  --db runtime/db/dev.db \
  --thresholds title_rate=0.95,body_100_rate=0.95,metadata_rate=0.30
```

### 4.5.1 red 前排查

如果 live smoke 或 audit 失败，不能立即收口 red。必须先完成并在 eval 中记录：

1. 删除 `runtime/db/dev.db*` 后重跑 live smoke，排除旧 checkpoint / 续抓状态污染。
2. 单独 `curl` seed URL，记录 HTTP 状态、content-type、响应体是否含目标列表数据。
3. 单独调用 `parse_list(seed_response, seed_url)`，确认 `detail_links` 数量；若为 0，
   回到 JS/CDN/API/feed/SSR 探查，不得直接写 `render_required`。
4. 单独 `curl` 一个详情 URL，并调用 `parse_detail`，确认 title、body、metadata 命中。
5. parser 单独可用但 runner 无数据时，优先检查 seed URL、scope、robots、runtime DB
   checkpoint 和 `ADAPTER_META.list_url_pattern`，不得先归咎于源站或 infra。
6. 只有上述检查完成且仍无法满足 gates，才允许 red；red 必须写明失败 gate、
   `last_error_kind`、复现命令和下一轮最小动作。

green 条件：

| 检查 | 要求 |
|---|---|
| pytest | 既有 + 新增全绿 |
| registry | 能 resolve 当前 host |
| workflow docs | Plan / Task / Eval 三件套存在 |
| task JSON | Task 文件是标准 JSON 且满足 `pr-task-file` 必备字段 |
| golden | 覆盖型配对样本通过：≥1 list、≥3 detail；有分页信号时 ≥1 pagination/list_2 |
| detail_url_pattern | live smoke 入库 URL 至少 95% 匹配当前 adapter 的 `ADAPTER_META.detail_url_pattern` |
| source capability | 已记录 API/SSR/headless 选择依据；若 infra helper 不覆盖但有静态信号，adapter fallback 已实现并测试 |
| live smoke | `raw_records_written >= 1` 且 `errors == 0` |
| audit | 退出码 0；默认包含 `title_rate`、`body_100_rate`、`metadata_rate`、`script_noise_rate_max` |
| 合规 | 无 robots/challenge/captcha/auth/paywall 绕过行为 |

### 4.6 eval

写：

`docs/eval-test/codegen-<host>-YYYYMMDD.md`

必填：

- 判定：`green` / `red` / `partial`
- 复现命令：完整 gates 命令
- audit stdout：完整粘贴
- smoke 指标：raw_records、errors、anti_bot_events、host/cohort 分布
- source capability 记录：probe verdict、API/SSR/headless 选择依据、infra helper 是否覆盖；
  若写了 adapter fallback，说明 fallback 规则、测试覆盖与是否建议另开 infra 任务提升
- 文件清单：本次新增/修改的 plan/task/code/golden/test
- PR handoff：若 green，写建议 PR 标题和 body；若 red，写下一轮动作
- notify-message 草稿：邮件/IM 尚未接入，只写一段可复制的消息

wrapper 会复核本文件；若 eval 缺失，wrapper 会自动创建 red eval；若 eval
已存在，wrapper 会追加最终 gate 表、失败项、opencode exit code、日志路径与
worktree 路径。

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
