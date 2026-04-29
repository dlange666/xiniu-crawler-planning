# Codegen 输出契约 · 适配器结构 / Sink Schema / Harness 门槛 / Prompt 框架

> **版本**：rev 16 · **最近修订**：2026-04-29 · **状态**：active
> **实施状态**：M3.5 codegen-bootstrap 实施（关联 plan-20260428-codegen-bootstrap）

> 本 spec 规定 codegen 平台（OpenCode CLI 等编码 agent）产出的适配器代码
> 必须遵守的：内部架构、配套产物、默认 sink schema、harness 最低门槛、
> prompt 模板拆分。借鉴上一版 OpenCode 实施经验。
>
> 适用对象：所有 `domains/<context>/<source>/<source>_adapter.py`（codegen 产出 + 人手编写共用此契约）。

## 1. 设计原则

- **per-host 共享 adapter**：一个 host 一个文件，被多个 task 复用，避免代码爆炸。
- **adapter 文件内部强结构**：必备 hook 协议 + 元信息 + 配套产物，让 harness 可做强结构验证。
- **adapter 不持有 infra**：纯 hook，由通用 `crawl/parse/sink` 编排器调用。
- **prompt = system + user 两份模板**：技术规范不变，任务参数变化。

## 2. Adapter 文件内部架构

源目录：`domains/<context>/<source>/`。同一源的 adapter、seed、golden 全部
放在同一目录下，避免 `adapters/`、`seeds/`、`golden/` 横向分散。
`<source>` 使用 wrapper 计算出的 canonical host slug，必须承载源站主体职责，
不得直接使用 `www`、`wap`、`m`、`mobile` 等通用渠道前缀；例如
`wap.miit.gov.cn` 写入 `domains/gov_policy/miit/miit_adapter.py`，
`search.sh.gov.cn` 写入 `domains/gov_policy/sh_search/sh_search_adapter.py`。

单文件：`domains/<context>/<source>/<source>_adapter.py`。文件必须包含以下要素（缺一即被 harness 拦截）。

### 2.1 ADAPTER_META

```python
ADAPTER_META: dict = {
    "host": "www.ndrc.gov.cn",
    "schema_version": 1,                 # 站点 DOM 改版时 bump
    "data_kind": "policy",               # policy | news | regulation | ...
    "supported_modes": ["full", "incremental"],
    "list_url_pattern": "https://www.ndrc.gov.cn/xxgk/zcfb/.*",
    "detail_url_pattern": "https://www.ndrc.gov.cn/xxgk/.*\\.html",
    "last_verified_at": "2026-04-28",
    "owner_context": "gov_policy",
}
```

### 2.2 必备 hook（pure functions，不持有 infra）

```python
def build_list_url(seed: SeedSpec, page: int) -> str: ...
def parse_list(html: str, url: str) -> ParseListResult: ...
def parse_detail(html: str, url: str) -> ParseDetailResult: ...
```

`SeedSpec` / `ParseListResult` / `ParseDetailResult` 在 `domains/<context>/model/` 中定义。

### 2.3 可选 hook

```python
def should_render(html: str, url: str) -> bool: ...        # 渲染判定
def extract_validators(headers: dict) -> dict: ...         # 返回 etag/last-modified
def normalize_url(url: str) -> str: ...                    # 站点专属 URL 规范化
```

### 2.4 禁忌（harness 合规扫描）

- 不得 import `infra/http` / `infra/storage` / `infra/frontier`（这些由通用编排器调用，hook 只接受字符串入参）
- 不得 import 其他业务域
- 不得在 hook 内发起网络请求
- 不得使用 `captcha_solver` / `stealth` / `undetected_chromedriver` / 任何反爬绕过库

## 3. 配套产物

每新增或改动 adapter，同 PR 内必备：

| 产物 | 路径 | 数量 / 要求 |
|---|---|---|
| Golden HTML | `domains/<context>/<source>/<source>_golden_*.html` | 覆盖型固定快照：≥1 list、≥3 detail；有分页信号时 ≥1 pagination/list_2 |
| Golden JSON | `domains/<context>/<source>/<source>_golden_*.golden.json` | 与 HTML 一一同名配对，禁止用聚合 JSON 替代配对样本 |
| 单元测试 | `tests/<context>/test_<source>_adapter.py` | 覆盖 registry、list、detail、metadata、pagination（如适用） |
| Seed YAML | `domains/<context>/<source>/<source>_seed.yaml` | 包含 `entry_urls`、`politeness_rps`、`crawl_mode` 默认值 |
| Plan / Task / Eval 文件 | 见下文 §3.1 | 任何 codegen 调用都必须配套，缺即拒绝合入 |

### 3.1 Codegen 调用规约（rev 3 引入）

Coding agent（opencode / claude-code / codex / mock）的 SKILL.md 体系**不会**被 opencode CLI 等外部 agent 自动加载。为避免每次手动调用 agent 时漏走工作流，本仓库强制：

1. **Pipeline 加载**：任何 coding agent 调用必须挂载 `docs/codegen-pipeline.md` 作为系统级约束（opencode 用 `-f docs/codegen-pipeline.md`，其它 agent 走等价机制）。Pipeline 内容是**硬规则**，包括 git-worktree、plan、task、允许写入范围、infra capability 索引、契约要点、验收门、eval、PR handoff、merge 边界与 notify-message 草稿。
2. **Plan / Task / Eval 三件套**：每次 codegen 调用必须同步产出：
   - `docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md`
   - `docs/task/active/task-codegen-<host>-YYYY-MM-DD.json`
   - `docs/eval-test/codegen-<host>-YYYYMMDD.md`
   其中 Task 文件由 wrapper 预生成合法 `pr-task-file` JSON 骨架，agent 只更新
   字段值。wrapper 在 gates 中必须校验该文件可被标准 JSON parser 解析，并
   满足 `docs/task/template.md` 的必备字段；常见的 markdown fence / 前后解释
   文本包裹 JSON 可由 wrapper 自动抽取并规范化，仍失败则 `task_json` gate red。
3. **Live smoke 强制**：eval 判定 `green` 当且仅当：
   (a) `scripts/run_crawl_task.py --max-pages 30` 跑出 `raw_records_written ≥ 1` 且 `errors == 0`；
   (b) `scripts/audit_crawl_quality.py` 退出码 0（默认阈值：`title_rate ≥ 95%` / `body_100_rate ≥ 95%` / `metadata_rate ≥ 30%`，业务域可调）。
   仅契约/结构性测试通过 → 判 `red`（避免 codegen "形似而神不至"）。
4. **失败必报告与自主迭代**：跑不通时，eval §5 用 pipeline 的失败模板列出失败信号 + 根因判断 + 建议下一步，不允许无声继续。wrapper 必须把失败 gate、pytest 输出、audit short body sample、script noise sample、detail URL pattern miss 回灌给 coding agent，最多 3 轮；3 轮后仍失败才最终 red。
5. **解析质量硬约束**：`source_metadata` 必须为 `SourceMetadata(raw={...})`；`body_text` 不得夹带 JS/CSS/DOM 脚本噪声；`detail_links` 必须在业务 scope 内，非业务的导航、搜索、社媒、移动入口不得靠降低 gate 通过。
6. **能力缺口 fallback**：当 infra helper 不覆盖但页面存在明确、稳定、可静态解析的分页/API/字段信号时，coding agent 不得直接判 red 或 `render_required`；必须先在当前 source 的 domain adapter 内实现有界 fallback，并用 golden/test/eval 记录。codegen 任务仍不得修改 `infra/`；可复用能力由单独 infra 任务提升。
7. **未来自动化**：本规约目前由调用方人工执行；`infra/codegen/` worker 落地后必须接管 1–6 步，使其不可绕过（spec `codegen-bootstrap`）。

8. **受控探查工具**（rev 6 引入）：coding agent 不得自行把探查样本写到
   `/tmp` 或直接在 adapter hook 内联网。每个站点先调用：

   ```bash
   uv run python scripts/probe_source.py \
     --url <entry_url> \
     --host <host> \
     --mode auto \
     --out runtime/probe/<host_slug>/
   ```

   agent 必须基于 `probe-result.json` 和 `runtime/probe/<host_slug>/` 下的
   artifact 选择 capability。探查流程仍遵循低成本到高成本递进；但一旦发现
   稳定、robots 允许、可回放的公开 JSON/API artifact，采集优先级为
   `json_api -> static_html/SSR -> headless_required`。当 probe 返回
   `robots_disallow` / `blocked` / `fetch_failed` 时，本轮 codegen 必须写
   `red`，不得绕过保护措施。`headless_required` 只表示需要后续 render-pool
   能力；当前不得自行引入 Playwright/Selenium 或 stealth 工具。

> 本规约由 2026-04-28 的 MIIT codegen 试验暴露的"opencode 不读 SKILL.md、漏写 plan/task/eval"问题驱动。试验报告：`docs/eval-test/codegen-trial-miit-20260428.md`（待补）。

## 4. 默认 Sink Schema · `crawl_raw`

> **DDL 权威源**：`docs/prod-spec/data-model.md` §4.2.3（`crawl_raw`）+ §4.2.4（`crawl_run_log`）。本节保留设计动机说明，不再维护 DDL，以避免双源不一致。

所有业务域共享的 raw 落库表。Adapter **不直接写库**；由通用 `domains/<context>/sink/`
调 `infra/storage/` 落到此表。业务域可在 raw 之上扩展业务表（如 `policy_doc`），
但 raw 层结构不可变。

关键字段语义（DDL 见 data-model.md §4.2.3）：

- `data` JSON —— **仅此一处保留 JSON**：adapter 输出结构因 host 而异，平铺到列不可行
- `content_sha256` —— 配合 `infra-resilience.md` 解析层去重
- `etag` / `last_modified` —— 配合 §1 增量抓取（HTTP 304）
- `raw_blob_uri` —— 配合 OSS 原始页可回放
- `url_hash` —— 唯一键，跨任务 URL 级别去重

## 5. Harness 最低门槛（强制基线）

`infra/harness/` 在跑业务域注入的更高门槛之前，强制执行以下基线，缺一即拦截。

### 5.1 文件完整性

| 检查 | 必备 |
|---|---|
| Adapter 文件 | `domains/<context>/<source>/<source>_adapter.py` 存在 |
| ADAPTER_META | 含全部必备字段（§2.1） |
| Hook 完整 | `build_list_url`、`parse_list`、`parse_detail` 三 hook 全部定义 |
| 类型签名 | hook 入参/返回类型与协议一致（mypy 通过） |
| Golden | 覆盖型配对样本：≥1 list、≥3 detail；有分页信号时 ≥1 pagination/list_2 |
| 单元测试 | `tests/<context>/test_<source>_adapter.py` 存在且 `pytest` 全绿 |
| Seed YAML | 含 `entry_urls` 与 `politeness_rps`（不得高于 fetch-policy 默认） |
| 合规扫描 | 不含禁忌词（§2.4） |

### 5.2 端到端（dev profile）

| 检查 | 通过条件 |
|---|---|
| 跑通 | adapter 能解析至少 1 个真实详情页（带网络） |
| 写库 | `SELECT COUNT(*) FROM crawl_raw WHERE task_id=? AND business_context=?` ≥ 1 |
| Schema 合格 | `data` 字段经业务侧 JSON schema 校验合格率 100%（小样本） |
| robots 检查 | 实抓 robots，对 host 未设 disallow |

### 5.3 失败处理

任何一项不过 → harness 返回 `failed`，codegen worker 把结构化失败摘要回喂 agent
（最多 3 轮）；摘要至少包含失败 gate、pytest traceback、audit short body sample、
script noise sample、detail URL pattern miss、golden coverage 错误。3 轮全失败 →
task 状态 `failed`。

失败写回任务表时，状态机字段与原因字段必须分离：

- `crawl_task_execution.status='failed'`
- `last_run_status='red'` 或 `partial`
- `last_error_kind` 使用 `data-model.md` §4.1.3 的枚举建议
- `last_error_detail` 写明失败 gate、入口 URL、关键观测
- `last_eval_path` 指向 `docs/eval-test/codegen-<host>-YYYYMMDD.md`
- 需要改 PRD seed、scope、合规策略或人工确认源站时，`needs_manual_review=1`

## 6. Prompt 框架

### 6.1 模板拆分

| 模板 | 路径 | 内容 | 何时变化 |
|---|---|---|---|
| system | `infra/agent/prompts/system.j2` | 技术规范、决策流程、Adapter 架构、Harness 门槛、禁忌 | 仓库级演进；rev bump 触发回归 |
| user | `infra/agent/prompts/user.j2` | 单 task 的参数：site_url / data_kind / sample_urls / scope / constraints | 每 task 注入 |

### 6.2 System prompt 必含决策流程（步骤 1–5）

借鉴上一版 OpenCode 实践：

1. **页面渲染分析**：先调用 `scripts/probe_source.py --mode auto`；HTML 直含数据 → 静态；否则进步骤 2
2. **API 优先**：probe 若发现 JSON/API artifact，adapter 基于该响应结构实现；优先级高于 static HTML / SSR / headless；不得在 hook 内自行请求 API
3. **Playwright 兜底**：probe 返回 `headless_required` 时写 red/后续行动；只有 render-pool spec 实施后才可启用
4. **翻页 + 采集模式**：必须实现翻页循环；硬上限 = `task.spec.constraints.max_pages_per_run`；增量模式用 ETag/Last-Modified（传输层）+ crawl_mode/crawl_until（应用层）
5. **数据结构分析**：CSS/XPath 选择器；字段类型 + 必填/可选

### 6.2.1 System prompt 必含质量自检

agent 收口前必须自检：

- `ParseDetailResult.source_metadata` 使用 `SourceMetadata(raw={...})`，测试读取 `.raw`
- `body_text` 不含 `var ... =`、`function`、`document.`、`window.`、`<script`、
  `</script`、`$(...)` 等脚本污染
- audit short body sample 的 URL 均属于业务 scope；非业务链接已过滤
- `detail_url_pattern` 能匹配 live smoke 入库 URL 的至少 95%
- golden 为一一配对样本，覆盖 list/detail/pagination（如适用），且由当前 adapter 输出重生成
- pagination URL 按自然页码排序

### 6.3 User prompt 必含字段

```
- 项目名：{{ business_context }}/{{ host }}
- 目标 URL：{{ task.spec.site_url }}
- 范围：{{ task.spec.scope_description }}
- 数据字段：参见 docs/prod-spec/{{ business_context }}.md（agent 必读）
- 速率：{{ task.spec.constraints.politeness_rps }}
- 翻页上限：{{ task.spec.constraints.max_pages_per_run }}
- 采集模式：{{ task.spec.crawl_mode }}
- 截止日期：{{ task.spec.crawl_until | default(none) }}
- 输出：写入 crawl_raw（task_id={{ task.task_id }}, business_context={{ business_context }}）
- 沙箱白名单：{{ allowed_paths | join('\n  ') }}
```

### 6.4 Prompt 版本与回归

`system.j2` 文件顶部带版本号注释（如 `{# system-prompt v3 #}`）。bump 即：
- 本 spec 追加修订历史
- 安排 1–2 个稳定 host 跑回归（agent 重新产出 → 与 main 上版本 diff 行数 ≤ 30%）

## 7. 与其他 spec 的关系

| 关系 | spec |
|---|---|
| Task 模型字段（`crawl_mode` 等）来源 | `docs/research/design-task-driven-codegen-20260427.md` §3 |
| 默认 sink 表落库实现 | `infra/storage/` + `domains/<context>/sink/` |
| 解析层去重消费 `content_sha256` | `docs/prod-spec/infra-resilience.md` |
| Harness 调度规则 | `docs/research/design-task-driven-codegen-20260427.md` §6 |
| Sandbox 白名单 | `docs/research/design-task-driven-codegen-20260427.md` §6 step 6 |
| 多实例并发竞争 | `docs/prod-spec/infra-deployment.md` §4 |

## 8. 不在本 spec 范围

- 业务域具体字段定义（在各业务域 spec 中）
- prompt 文本本身（在 `infra/agent/prompts/` 中，本 spec 仅约束模板结构与必含字段）
- agent 子进程调用参数（在 `docs/research/design-task-driven-codegen-20260427.md` §5）

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 16 | 2026-04-29 | 落地 `crawl_task_generation` 表（spec data-model §4.1.2）：wrapper 在 claim 时写 `claimed`、调 opencode 前写 `drafting`、gates 完成写 `merged`/`failed`；codegen 过程状态从 `crawl_task_execution` 中分离，避免"开发完成"和"爬取完成"语义混淆。WebUI `/api/tasks` 暴露 `adapter_ready`（来自 `adapter_registry`）和 `generation_status`，列表三层并列展示 | `infra/storage/sqlite_store.py`、`infra/codegen/task_db.py`、`webui/`、`data-model.md` §4.1.2 |
| rev 15 | 2026-04-29 | 把单文件 wrapper `scripts/run_codegen_for_adapter.py` 拆到 `infra/codegen/`（shell/paths/worktree/task_db/task_json/golden/prompt/opencode/gates/eval_writer/publish），入口改为 `scripts/run_codegen.py`；pipeline §1 澄清"agent 不修改 `infra/`"指 capability 模块，不含 `infra/codegen/` wrapper 自身 | `infra/codegen/`、`scripts/run_codegen.py`、`docs/codegen-pipeline.md` §1 |
| rev 14 | 2026-04-29 | 强化 codegen 失败闭环与质量门：wrapper red 自动回灌失败证据最多 3 轮；golden 从数量门槛改为覆盖型配对门槛；新增 SourceMetadata、正文脚本污染、业务 scope/detail_url_pattern、audit sample 自检要求 | `docs/codegen-pipeline.md`、`scripts/run_codegen_for_adapter.py`、`scripts/audit_crawl_quality.py` |
| rev 13 | 2026-04-29 | 明确 codegen agent 在 infra helper 不覆盖但静态信号明确时，必须在 domain adapter 内实现有界 fallback，且禁止在 codegen 任务中修改 infra；同时将常见 `createPageHTML(container_id,total,cur,prefix,suffix,rows)` 变体提升到 infra pagination helper | `docs/codegen-pipeline.md`、`scripts/run_codegen_for_adapter.py`、`infra-crawl-engine.md` rev 4 |
| rev 12 | 2026-04-29 | 强化 codegen 收口协议：agent 必须完整执行 pytest/registry/task_json/golden/live_smoke/audit；live smoke 前清理 `runtime/db/dev.db*`；red 前必须排查 seed、parse_list、parse_detail、scope/robots/checkpoint，避免把 JS shell 或旧 checkpoint 误判为 render/infra 问题 | `docs/codegen-pipeline.md`、`scripts/run_codegen_for_adapter.py` |
| rev 11 | 2026-04-29 | 将 domain 源产物从横向目录 `adapters/`、`seeds/`、`golden/` 调整为源聚合目录 `domains/<context>/<source>/`；adapter/seed/golden 文件使用 `<source>_*` 前缀命名；registry 兼容扫描旧路径但新 codegen 只写新路径 | `infra/adapter_registry/registry.py`、`docs/codegen-pipeline.md`、`scripts/run_codegen_for_adapter.py` |
| rev 10 | 2026-04-29 | 将 codegen 默认 audit 正文长度门从 `body_500_rate` 调整为 `body_100_rate`，避免短通知/公告类合法页面被错误判 red；长正文质量仍保留为观测指标 | `scripts/audit_crawl_quality.py`、`docs/codegen-pipeline.md` |
| rev 9 | 2026-04-29 | 明确 adapter 文件名必须使用源站主体 slug，禁止把 `wap`/`www`/`m` 等通用渠道前缀作为文件名；wrapper slug 规则同步修正 | `scripts/run_codegen_for_adapter.py`、`docs/codegen-pipeline.md` |
| rev 8 | 2026-04-29 | 强化 Task JSON 输出契约：wrapper 预生成标准 `pr-task-file` 骨架，gates 校验并规范化常见包裹文本，无法修复时以 `task_json` gate red 记录到 eval | `scripts/run_codegen_for_adapter.py`、`docs/codegen-pipeline.md` |
| rev 7 | 2026-04-29 | 新增受控 source probe 调用规约：codegen 必须先用 `scripts/probe_source.py` 在 repo `runtime/probe/` 下留存 artifact，再选择 static / JSON API / headless_required；禁止把探查样本写 `/tmp` 或在 hook 内联网 | `scripts/probe_source.py`、`infra/source_probe/`、`docs/codegen-pipeline.md` |
| rev 6 | 2026-04-29 | 明确 codegen red/partial 必须把结构化失败原因写回 `crawl_task_execution`：状态机字段仅表示 failed/red，具体原因进入 `last_error_kind/detail/eval_path/needs_manual_review` | `data-model.md` rev 3、`docs/codegen-pipeline.md` §4.6 |
| rev 5 | 2026-04-28 | 将 `docs/codegen-brief.md` 升级并更名为 `docs/codegen-pipeline.md`；明确 codegen 模拟 workflow-execution 的顺序：git-worktree → plan → task → code/gates → eval → PR handoff → merge 边界 → notify-message 草稿；消除“禁止写 docs”与 Plan/Task/Eval 三件套之间的冲突；单元测试路径收敛为 `tests/<context>/test_adapter_<host>.py`（rev 11 起调整为 `tests/<context>/test_<source>_adapter.py`） | `docs/codegen-pipeline.md`、`scripts/run_codegen_for_adapter.py` |
| rev 4 | 2026-04-28 | §3.1.3 把 live smoke 阈值从"raw_records ≥ 1"升级为"raw_records ≥ 1 且 audit 脚本退出码 0"；引入 `scripts/audit_crawl_quality.py` 作为确定性质量门 —— 由 MoF codegen 试验暴露的"假 green"问题驱动（agent 自报 green 但 metadata 命中率 0%） | `scripts/audit_crawl_quality.py` 新建；原 brief §2/§4/§5 强化 |
| rev 3 | 2026-04-28 | 新增 §3.1 Codegen 调用规约：强制加载 `docs/codegen-brief.md`、强制 plan/task/eval 三件套、live smoke 强制、失败必报告 —— 由 MIIT codegen 试验暴露的"opencode 不读 SKILL.md"问题驱动；rev 5 起由 `docs/codegen-pipeline.md` 继承 | `docs/codegen-brief.md` 新建，rev 5 更名 |
| rev 2 | 2026-04-28 | §4 把 DDL 移交 `data-model.md` §4.2.3/§4.2.4 为权威源，本节仅保留设计动机 | data-model.md 创建 |
| rev 1 | 2026-04-28 | 初稿 —— 借鉴上一版 OpenCode 实施：内部架构强约束（ADAPTER_META + hook 协议）、配套产物、默认 raw sink schema、harness 最低门槛、prompt system+user 拆分 | — |
