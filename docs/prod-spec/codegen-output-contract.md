# Codegen 输出契约 · 适配器结构 / Sink Schema / Harness 门槛 / Prompt 框架

> **版本**：rev 2 · **最近修订**：2026-04-28 · **状态**：active
> **实施状态**：M3.5 codegen-bootstrap 实施（关联 plan-20260428-codegen-bootstrap）

> 本 spec 规定 codegen 平台（OpenCode CLI 等编码 agent）产出的适配器代码
> 必须遵守的：内部架构、配套产物、默认 sink schema、harness 最低门槛、
> prompt 模板拆分。借鉴上一版 OpenCode 实施经验。
>
> 适用对象：所有 `domains/<context>/adapters/<host>.py`（codegen 产出 + 人手编写共用此契约）。

## 1. 设计原则

- **per-host 共享 adapter**：一个 host 一个文件，被多个 task 复用，避免代码爆炸。
- **adapter 文件内部强结构**：必备 hook 协议 + 元信息 + 配套产物，让 harness 可做强结构验证。
- **adapter 不持有 infra**：纯 hook，由通用 `crawl/parse/sink` 编排器调用。
- **prompt = system + user 两份模板**：技术规范不变，任务参数变化。

## 2. Adapter 文件内部架构

单文件：`domains/<context>/adapters/<host>.py`。文件必须包含以下要素（缺一即被 harness 拦截）。

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
| Golden HTML | `domains/<context>/golden/<host>/*.html` | ≥ 5 个固定快照 |
| Golden JSON | `domains/<context>/golden/<host>/*.golden.json` | 与 HTML 一一配对 |
| 单元测试 | `tests/<context>/adapters/test_<host>.py` | 跑 5 个 golden 用例全绿 |
| Seed YAML | `domains/<context>/seeds/<host>.yaml` | 包含 `entry_urls`、`politeness_rps`、`crawl_mode` 默认值 |

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
| Adapter 文件 | `domains/<context>/adapters/<host>.py` 存在 |
| ADAPTER_META | 含全部必备字段（§2.1） |
| Hook 完整 | `build_list_url`、`parse_list`、`parse_detail` 三 hook 全部定义 |
| 类型签名 | hook 入参/返回类型与协议一致（mypy 通过） |
| Golden | `golden/<host>/` ≥ 5 个 `.html` + `.golden.json` 配对 |
| 单元测试 | `tests/<context>/adapters/test_<host>.py` 存在且 `pytest` 全绿 |
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

任何一项不过 → harness 返回 `failed`，codegen worker 把失败摘要回喂 agent
（最多 3 轮）；3 轮全失败 → task 状态 `failed`。

## 6. Prompt 框架

### 6.1 模板拆分

| 模板 | 路径 | 内容 | 何时变化 |
|---|---|---|---|
| system | `infra/agent/prompts/system.j2` | 技术规范、决策流程、Adapter 架构、Harness 门槛、禁忌 | 仓库级演进；rev bump 触发回归 |
| user | `infra/agent/prompts/user.j2` | 单 task 的参数：site_url / data_kind / sample_urls / scope / constraints | 每 task 注入 |

### 6.2 System prompt 必含决策流程（步骤 1–5）

借鉴上一版 OpenCode 实践：

1. **页面渲染分析**：curl + 源码 grep；HTML 直含数据 → 静态；否则进步骤 2
2. **API 优先**：DevTools Network 找 XHR/Fetch；找到 JSON → httpx 直请；强加密 → 步骤 3
3. **Playwright 兜底**：仅在前两步不可行时启用；显式等待目标元素
4. **翻页 + 采集模式**：必须实现翻页循环；硬上限 = `task.spec.constraints.max_pages_per_run`；增量模式用 ETag/Last-Modified（传输层）+ crawl_mode/crawl_until（应用层）
5. **数据结构分析**：CSS/XPath 选择器；字段类型 + 必填/可选

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
| rev 2 | 2026-04-28 | §4 把 DDL 移交 `data-model.md` §4.2.3/§4.2.4 为权威源，本节仅保留设计动机 | data-model.md 创建 |
| rev 1 | 2026-04-28 | 初稿 —— 借鉴上一版 OpenCode 实施：内部架构强约束（ADAPTER_META + hook 协议）、配套产物、默认 raw sink schema、harness 最低门槛、prompt system+user 拆分 | — |
