# Codegen Agent Brief（每次 codegen 必加载）

> 适用对象：opencode / 其它 coding agent CLI。
> 调用方式：`opencode run -m <model> -f docs/codegen-brief.md -f .codegen-prompt.md`
> 本文件是**硬约束**，违反任何一条都视为 PR 直接拒。

---

## 0. 你的角色

你是受限的代码生成 agent，本次任务是**为单个 host 实现一个采集适配器**。

**只能新增** 这三类文件：

- `domains/<business_context>/adapters/<host>.py`
- `domains/<business_context>/seeds/<host>.yaml`
- `tests/<business_context>/test_adapter_<host>.py`

**禁止修改** 任何其它文件，特别是：

```
infra/         (跨域 infra，统一约束所有 adapter，不归你管)
docs/          (规格文档由人审)
AGENTS.md      (仓库总规则)
CLAUDE.md      (Claude Code 规则)
pyproject.toml (依赖管理)
其它已有 adapter (不许"顺手优化")
```

---

## 1. Adapter 契约

完整规则见 `docs/prod-spec/codegen-output-contract.md`，要点：

- **样例参考**：`domains/gov_policy/adapters/ndrc.py`（生产中验证过的样例，照着改）
- **元数据校验**：`infra/adapter_registry/meta.py` 的 `REQUIRED_KEYS` / `VALID_RENDER_MODES`
- **类型定义**：`infra/crawl/types.py`（`ParseListResult` / `ParseDetailResult` / `Attachment` / `SourceMetadata` / `SeedSpec`）

钩子签名（**必须严格匹配**）：

```python
def parse_list(html: str, url: str) -> ParseListResult: ...
def parse_detail(html: str, url: str) -> ParseDetailResult: ...
```

---

## 2. infra 能力索引（**不要重新实现**）

> **核心边界**：adapter 是**纯函数**——输入 HTML 字符串 + URL 字符串，输出
> `ParseListResult` / `ParseDetailResult`。**不调 HTTP，不持有任何 IO**。
> 实际的"采集"由 `infra/crawl/CrawlEngine` 驱动，把 HTML 喂给你的纯函数。

### 2.1 你**不用关心**（infra 自动做）

| 能力 | 实现在 | 引擎如何用它 |
|---|---|---|
| HTTP / UA / Retry-After / per-host token bucket | `infra/http/` | 自动节流 + 重试 |
| robots.txt（RFC 9309）| `infra/robots/` | 入口前置拦截 |
| 反爬识别（401/403/WAF/captcha → host cooldown）| `infra/http/` | 命中即止损 |
| Scope 准入（same_origin / same_etld_plus_one / url_pattern / allowlist）| `infra/crawl/scope.py` | 引擎按 `task.scope_mode` 自动滤 |
| 调度 BFS / DFS / 优先级堆 | `infra/frontier/` + `infra/crawl/strategies.py` | 按 depth + base_score 自动排序 |
| 续抓 checkpoint（重启不重抓）| `infra/crawl/runner.py` + `url_record.frontier_state` | 自动 |
| 去重（url_hash UNIQUE / content_sha256）| `infra/storage/` + `infra/crawl/dedup.py` | sink 层自动 |
| HTML → bytes 落 blob、JSON 落表 | 引擎统一处理 | 自动 |
| URL 类型路由（list_page / detail / interpret / attachment）| `infra/crawl/runner.py` | 按 `discovery_source` 自动派发 |

### 2.2 你**可以调用**的 helper（写 adapter 时直接用）

| Helper | 在 | 适用 |
|---|---|---|
| `parse_create_page_html` / `expand_create_page_html_pages` | `infra/crawl/pagination_helpers.py` | 政府站常见 `createPageHTML(N, ...)` JS 翻页脚本 |
| `detect_url_param_paginator` | 同上 | URL 带 `page=N` / `pageNum=N` 参数 |
| `detect_path_paginator` | 同上 | 路径分页 `index_2.html` / `list_3.html` |

### 2.3 你**必须自己写**的纯函数（核心活）

```python
def parse_list(html: str, url: str) -> ParseListResult:
    """从列表页 HTML 中：
    1. 抽 detail_links（到详情页的 URL）—— 这是 URL 发现的核心
    2. 抽 next_pages（翻页 URL）—— 漏一页 = 永久漏数据
    """

def parse_detail(html: str, url: str) -> ParseDetailResult:
    """从详情页 HTML 中：
    1. title           —— 必抽，不可空
    2. body_text       —— 去 nav/footer 后的纯文本，必抽（短文也要抽到）
    3. source_metadata —— 发文字号 / 发文机关 / 成文日期 / 发布日期 / 主题分类 / 索引号
                          见 docs/prod-spec/domain-<ctx>.md 字段表
    4. attachments     —— PDF / DOC / XLS / OFD / ZIP 链接
    5. interpret_links —— 同政策的解读 / 图解 / 答记者问 URL
    """
```

### 2.4 自检触发器（看到下面这些信号 = 你想错了，立即停下）

- 想写"调 httpx / requests" → 错，引擎做这事
- 想写"判断同 host" → 错，scope.py 做
- 想写"sleep / 限流" → 错，token bucket 做
- 想自己重发明 page=N 参数翻页 → 错，pagination_helpers 已经写好了
- 想 import `domains/` 下其它文件 → 错，业务域之间禁止依赖

---

## 3. 工作流（**opencode 不读 skills/，所以写在这里**）

本次代码生成必须配套产出 3 份记录文件，缺一不可：

### 3.1 Plan（开工前）

- 路径：`docs/exec-plan/active/plan-YYYYMMDD-codegen-<host>.md`
- 模板：`docs/exec-plan/template.md`
- 关键字段：目标、原子任务列表（至少含"实现 adapter"+"写测试"+"live smoke"三条）、关联 spec=`codegen-output-contract.md`

### 3.2 Task（开工前）

- 路径：`docs/task/active/task-codegen-<host>-YYYY-MM-DD.json`
- 模板：`docs/task/template.md`
- task_id 格式：`T-YYYYMMDD-NNN`，初始状态 `pending`，自己执行时推进到 `in_progress` / `verifying` / `completed`（或 `failed`）

### 3.3 Eval（验收后）

- 路径：`docs/eval-test/codegen-<host>-YYYYMMDD.md`
- 模板：`docs/eval-test/template.md`
- 必填：判定（`green` / `red` / `partial`）、§3 度量结果（契约通过率、live smoke 抓到的 raw_records 数、失败原因）、§5 异常案例、§7 后续行动

**没写这 3 份 = 任务未完成**。即使代码跑通了，也是 `red`。

---

## 4. 验收门（按顺序，前一项失败立即停）

```
1. uv run pytest tests/ -q                       # 既有测试不能破

2. uv run pytest tests/<ctx>/test_adapter_<host>.py -v   # 你新写的测试要绿

3. uv run python -c "from infra import adapter_registry; \
       adapter_registry.discover(); \
       print(adapter_registry.get('<ctx>', '<host>'))"   # 注册中心能解析

4. live smoke（足够样本 + 跨 cohort 多样性）：
   uv run python scripts/run_crawl_task.py \
       domains/<ctx>/seeds/<host>.yaml \
       --max-pages 30 --max-depth 1 --task-id 9999
   # ↑ 注意：--max-pages **必须 ≥ 30**，否则 audit 脚本统计不可信
   # ↑ 如果 seed 设了 scope_mode=same_etld_plus_one 等非默认值，
   #    CLI 必须显式 --scope-mode 同步（已知陷阱：CLI 默认值会覆盖 seed）

5. 质量审计（确定性，不靠 agent judgement）：
   uv run python scripts/audit_crawl_quality.py --task-id 9999 \
       --thresholds title_rate=0.95,body_500_rate=0.70,metadata_rate=0.30
   # 退出码 0 = pass，1 = fail
```

### 4.1 通过条件（**全部满足才能写 green**）

| 维度 | 阈值（gov_policy 默认） | 来源 |
|---|---|---|
| pytest 既有 + 新增 | 全绿 | 步骤 1+2 |
| registry 解析 | 抛不出 AdapterNotFound | 步骤 3 |
| `raw_records_written` | ≥ 1（来源步骤 4） | smoke 报告 |
| `errors`（来源步骤 4） | 0 | smoke 报告 |
| `audit_crawl_quality.py` 退出码 | 0 | 步骤 5 |
| → `title_rate` | ≥ 95% | audit 输出 |
| → `body_500_rate` | ≥ 70% | audit 输出 |
| → `metadata_rate` | ≥ 30% | audit 输出 |
| → 至少 1 个非空 cohort 的 `low_quality` 占比 ≤ 50% | 软提示 | audit `cohort_quality` 段 |

> **业务域可调阈值**：`domain-gov-policy.md` 等 spec 可声明更高的阈值
> （例如要求 `metadata_rate ≥ 80%`），把它们传给 `--thresholds`。

### 4.2 阈值未达 → 不允许 self-judge "差不多就行"

audit 脚本退出码 1 = eval 必须写 `red`，禁止：

- "metadata 0% 但其它都好，所以 partial green" ✗
- "选择器在大部分子站工作，少数子站例外" ✗
- "低质量记录是政策本身正文短，不是我抽错" —— **必须用 §5 失败回报模板证明**

**根本原则**：**质量判定权不在 agent 手里**。audit 脚本说 fail = fail；agent 不可申辩，只能：
(a) 改选择器再跑一轮（最多 3 轮），或
(b) 写完整失败回报 + eval=red，停下来让人介入。

---

## 5. 失败回报模板（跑不通或质量不达 → 严禁无声继续）

任何一道验收门未通过时，在 eval §5 必须用此格式回报：

```
## 5. 异常案例

### 5.1 整体失败信号
- 失败步骤: <步骤 1 pytest / 步骤 4 live smoke / 步骤 5 audit / ...>
- audit 输出（如步骤 5 跑过）: 完整粘贴 audit_crawl_quality.py 的 stdout
- raw_records_written: <数字>
- errors / anti_bot_events: <数字>

### 5.2 URL 发现层（适用于 detail_links / next_pages 漏抽）
- 列表页 URL: <实际跑的入口>
- HTML 总长: <bytes>
- 期望 detail 链接 ≥ N 条（按页面肉眼数）
- 实际 detail_links_discovered: <数字>
- 翻页期望 / 实际: <如有>
- 根因猜测: <选择器 mismatch / JS 渲染 / scope reject>

### 5.3 关键特征抽取层（适用于 metadata_rate / body_500_rate 不达）
对 audit 标记的低质量记录（short_body_samples），抽 1-2 条原始 HTML 看一眼：
- URL: <短 body 那条>
- 期望的字段（title/body/metadata）在 HTML 里**实际位于哪个 DOM 容器**
- adapter 当前选择器命中的容器 vs 实际容器
- 跨 cohort 差异: <这个子站用 X class，另一子站用 Y id>

### 5.4 根因分类（**必填**，多选一）
- [ ] 选择器假设错（应该改）→ 改选择器再跑一轮
- [ ] 站点是 JS 渲染（SSR 假设错）→ eval=red，建议升级 render_mode 或换站点
- [ ] 反爬命中（403/captcha）→ eval=red，**不重试不绕过**，转人工
- [ ] 多 cohort DOM 异质性（一个选择器顶不住）→ 写多分支选择器，或缩 scope
- [ ] 业务正常（如政策正文确实短，主体在 PDF 附件）→ **必须证明**：
       展示 5 条短 body 记录的 HTML，证明这些页面 attachments 应该被抽到，
       从而把"短 body"和"漏抽 attachment"分开判断

### 5.5 建议下一步
<具体的下一轮迭代动作；或停下让人介入>
```

### 5.1 迭代规则

- **最多 3 轮**：发现失败 → 按 5.4 判类 → 改 → 再跑步骤 4+5。第 3 轮还 fail = eval 写 red 停下
- **每轮独立可复现**：每轮跑完，audit 输出贴进 eval，对比上一轮指标提升 / 退化
- **不要绕过 audit**：禁止"不跑 audit 就声明 green"

### 5.2 业务正常 vs 抽取漏报的判定（重要）

不是所有"短 body"都是 bug。**MoF 试验暴露**：约 20% 的政策是"印发型"，正文是短封面信
（"现予印发，请遵照执行"），主体在 PDF 附件。这种情况下：

- body_text 短是**业务正常** ✓
- 但 attachments 应该被抽到（对应附件的 PDF 链接）✓

如果 body 短 **而且** attachments 也是 0 → 是漏抽，必须修。
如果 body 短 **但** attachments 抽到了 → 业务正常，可在 eval §5.4 用 attachments 命中率证明。

---

## 6. 通用代码风格

- 中文注释；注释写"为什么"而不是"做什么"
- 禁止 `try/except` 兜底吞异常 —— 让上层处理
- 禁止虚构字段 —— 抽不到的 metadata 就不写
- urljoin 必须用，不要手拼 URL
- bs4 用 `lxml` parser
- 类型注解全套（`from __future__ import annotations` 已默认）
- 不写 docstring 装饰；模块顶部一句话说明 + 入口 URL 即可

---

## 7. 调用约定（运维层面）

- 仓库根目录运行 opencode（不要 `cd` 到 worktree 之外）
- 每次 codegen 在独立 worktree 里：`git worktree add -b agent/codegen-<host> ../xiniu-crawler-codegen-<host> HEAD`
- 模型由调用方指定，本文件不写死
- 输出全部走 `Write` / `Edit` 工具；不要 `cat > file <<EOF`

---

## 8. 与其它文档的关系

| 你需要时去看 | 路径 |
|---|---|
| 完整 adapter 内部契约 | `docs/prod-spec/codegen-output-contract.md` |
| ADAPTER_META 校验细节 | `infra/adapter_registry/meta.py` |
| 数据落库的字段语义 | `docs/prod-spec/data-model.md` §4.2 |
| 业务域字段标准（gov_policy 36 字段等） | `docs/prod-spec/domain-<ctx>.md` |
| 仓库总规则 | `AGENTS.md` |

**不要主动读** `docs/research/`、`docs/architecture.md`、其它非必需文档——浪费 token，本 brief 已收敛你需要的所有信息。
