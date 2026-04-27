# PLAN-20260427-mvp-policy-crawler

## 1. 元信息

- **Plan ID**：`PLAN-20260427-MVP-POLICY-CRAWLER`
- **关联规格**：`docs/prod-spec/policy-graph-v1.md`
- **关联研究**：`docs/research/research-ai-first-crawler-system-20260427.md`、`docs/research/policy-graph-product-plan-20260427.md`、`docs/research/policy-data-sources-phase1-20260427.md`
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

把"政策图谱 v1"在爬虫侧建设成可演进的数据采集平台，分阶段交付 MVP → 多
源去重 → AI 结构化 → 全省覆盖 → 调度反爬 → 可观测性。本计划只列 **MVP
（M0–M3）阶段**的原子任务；M4 起的计划等 M3 关闭时再开下一份 plan。

对应研究报告 §7 实施路线：
- M0 项目骨架（≈0.5 周）
- M1 单源跑通：国务院文件库（≈2 周）
- M2 多源 + 解析层去重：8 个国务院部委（≈3 周）
- M3 AI 结构化：36 字段 JSON 写库（≈3 周）

## 3. 原子任务列表

| 任务 ID | 标题 | 实现细节 | 验证方式 | 状态 |
|---|---|---|---|---|
| T-20260427-101 | [project] 初始化 Python + uv 工程 | 创建 `pyproject.toml`、`.python-version`、`uv.lock`；锚定 Python 3.12；预置 ruff/pytest 基础配置；不引入业务依赖 | 仓库可 `uv sync` 通过；`uv run pytest -q` 在空套件上通过；CI 不在本任务范围 | `pending` |
| T-20260427-102 | [infra/storage] 抽象层（dev SQLite + prod PolarDB + OSS） | 在 `infra/storage/` 下定义 `MetadataStore` 与 `BlobStore` 协议；提供 `SqliteMetadataStore`、`LocalFsBlobStore` 实现；通过 `STORAGE_PROFILE=dev/prod` 切换 | 单元测试覆盖：写入/读取一条 url_record 与 raw_blob，dev profile 全部通过 | `pending` |
| T-20260427-103 | [infra/http] 基础 HTTP 客户端 | `infra/http/client.py`：UA、cookie jar、超时、Retry-After 解析、指数退避 + 抖动、host 礼貌性令牌（per-host token bucket） | 单元测试：mock 一个 429+`Retry-After: 2` 站点，验证至少等 2 秒；普通 200 通过 | `pending` |
| T-20260427-104 | [infra/robots] RFC 9309 实现 | 拉取 `/robots.txt`、缓存 24h、5xx → complete disallow；提供 `is_allowed(url, ua)` API | 单元测试覆盖 RFC 9309 五种典型情形（200 解析、404 全允许、5xx 全禁止、缓存命中、UA 匹配） | `pending` |
| T-20260427-105 | [infra/frontier] 单进程两级队列 | `infra/frontier/`：全局优先级堆 + per-host ready queue；三类令牌：host 礼貌性、domain 配额、任务预算；提供 `submit(url, priority, source)`、`next_ready()` API | 单元测试：提交 30 URL 跨 3 host，验证 host 公平性与冷却命中 | `pending` |
| T-20260427-106 | [domains/gov_policy/model + crawl] 任务模型与 seed 管理 | `domains/gov_policy/model/`：定义 Task / UrlRecord / FetchRecord 等领域实体；`domains/gov_policy/crawl/`：seed 加载器与派发流程；`domains/gov_policy/seeds/statecouncil.yaml` 列出国务院文件库入口；CLI `scripts/run_crawl_task.py` 把 seed 写入 frontier | `uv run scripts/run_crawl_task.py domains/gov_policy/seeds/statecouncil.yaml` 可派发首批 URL；DB 中可查到 task_spec 与 url_record | `pending` |
| T-20260427-107 | [domains/gov_policy/crawl] 国务院文件库 fetcher | 站点适配器：解析列表页分页、详情页 URL；下载详情页 HTML 与同页元数据表；附件 PDF 仅落盘 OSS（dev 走本地）；不做 PDF→文本 | 跑 100 条政策，全部原始字节通过 `infra/storage` 落盘；元数据表 + 正文 + 附件清单可被回放查询 | `pending` |
| T-20260427-108 | [domains/gov_policy/parse] 站点解析器 v1（国务院） | 把元数据表抽成 `source_metadata` 字典，正文抽成 `body_text`，附件清单抽成 `attachments`；调用 `dedup` 模块；输出 `model.PolicyParsed` | 单元测试：5 个固定快照页面解析结果与黄金 JSON 一致 | `pending` |
| T-20260427-109 | [domains/gov_policy/dedup] 解析层严格去重 | 联合键 `(policy_title_norm, pub_code, content_sha256)` 一致才去重；不一致全部保留；额外算 simhash64 仅入信号表 | 单元测试：构造转载关系（同 pub_code 同正文 / 同 pub_code 改动正文），验证只去重前者 | `pending` |
| T-20260427-110 | [domains/gov_policy/{crawl,parse}] 8 个国务院部委适配器 | 复用 §107/§108 模式，对发改委、工信部、财政部、国家金融监督管理总局、证监会、国资委、人民银行、其他 各做一份适配器；按需扩展解析器；适配器实现统一接口（`SiteAdapter`）便于按 host 分发 | 每部委跑 50 条，原始页落盘 100% + 解析合格率 ≥ 95% | `pending` |
| T-20260427-111 | [infra/ai] LLM 客户端与 prompt 框架 | `infra/ai/`：通用 LLM 客户端、prompt 模板装载、JSON schema 校验（jsonschema）；只放纯技术能力，不放 36 字段 prompt 文本 | 单元测试：mock 一个 LLM 后端，正反例 schema 校验全部通过 | `pending` |
| T-20260427-112 | [domains/gov_policy/extract + sink] 抽取流水线 | 把 36 字段 prompt 文本与 schema 放在 `domains/gov_policy/extract/prompts/v1.md` + `schemas/policy_doc_v1.json`（业务事实）；从 store 拉解析后的政策文本 → 调 `infra/ai` → 校验 → 通过 `sink` 写 PolarDB（dev: SQLite）`policy_doc` 表 | 跑 100 条政策，schema 合格率 ≥ 90%，关键 6 字段联合准确率 ≥ 95%（人工抽样 30 条） | `pending` |
| T-20260427-113 | [docs/eval-test] M3 验收报告 | 在 `docs/eval-test/` 写下 retained-vs-candidate 工件：抽样 30 条对照 prompt v1 vs v0（v0 = 仅元数据正则），覆盖关键字段准确率与 schema 合格率 | 工件存在且包含上述指标；Evaluator 签字 `green` | `pending` |

## 4. 边界护栏

- **不做**前端页面、订阅推送、用户态。
- **不做** PDF→文本（TD-001）。
- **不做** 多 worker / 分布式（单进程即可撑 MVP）。
- **不做** simhash 自动合并（TD-003）。
- **不做** 反爬绕过；命中即降速/暂停/人工。
- **不做** 31 省市的适配（M4 单独立项）。
- **不引入** 邮件、OTel、Prometheus（待 TD-002、TD-005 提升）。

## 5. 完成标准

`green` 仅当：

- 第 3 节 13 个任务全部 `completed`
- T-113 工件已存在且 Evaluator 签字 `green`
- `docs/prod-spec/policy-graph-v1.md` §7 中第 1/3/4/5 行指标在 MVP 抽样下达标
- 本文件移到 `docs/exec-plan/archive/2026-W18/`（按合入周）
