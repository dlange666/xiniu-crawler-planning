# plan-20260427-mvp-policy-crawler

## 1. 元信息

- **Plan ID**：`plan-20260427-mvp-policy-crawler`
- **关联规格**：`docs/prod-spec/domain-gov-policy.md`
- **关联研究**：`docs/research/research-ai-first-crawler-system-20260427.md`、`docs/prd/policy-graph-product-plan-20260427.md`、`docs/prd/policy-data-sources-phase1-20260427.md`
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

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式 | 状态 |
|---|---|---|---|---|---|
| T-20260427-101 | [project] 初始化 Python + uv 工程 | — | 创建 `pyproject.toml`、`.python-version`、`uv.lock`；锚定 Python 3.12；预置 ruff/pytest 基础配置；不引入业务依赖 | 仓库可 `uv sync` 通过；`uv run pytest -q` 在空套件上通过；CI 不在本任务范围 | `pending` |
| T-20260427-102 | [infra/storage] 抽象层（dev SQLite + prod PolarDB + OSS） | `data-model.md` §6 | 在 `infra/storage/` 下定义 `MetadataStore` 与 `BlobStore` 协议；提供 `SqliteMetadataStore`、`LocalFsBlobStore` 实现；通过 `STORAGE_PROFILE=dev/prod` 切换 | 单元测试覆盖：写入/读取一条 url_record 与 raw_blob，dev profile 全部通过 | `pending` |
| T-20260427-103 | [infra/http] 基础 HTTP 客户端 | `infra-fetch-policy.md` §2.1, §3 | `infra/http/client.py`：UA、cookie jar、超时、Retry-After 解析、指数退避 + 抖动、host 礼貌性令牌（per-host token bucket） | 单元测试：mock 一个 429+`Retry-After: 2` 站点，验证至少等 2 秒；普通 200 通过 | `pending` |
| T-20260427-104 | [infra/robots] RFC 9309 实现 | `infra-fetch-policy.md` §4 | 拉取 `/robots.txt`、缓存 24h、5xx → complete disallow；提供 `is_allowed(url, ua)` API | 单元测试覆盖 RFC 9309 五种典型情形（200 解析、404 全允许、5xx 全禁止、缓存命中、UA 匹配） | `pending` |
| T-20260427-105 | [infra/frontier] 单进程两级队列 | `infra-fetch-policy.md` §2.1, §2.2 | `infra/frontier/`：全局优先级堆 + per-host ready queue；三类令牌：host 礼貌性、domain 配额、任务预算；提供 `submit(url, priority, source)`、`next_ready()` API | 单元测试：提交 30 URL 跨 3 host，验证 host 公平性与冷却命中 | `pending` |
| T-20260427-106 | [domains/gov_policy/model + crawl] 任务模型与 seed 管理 | `data-model.md` §4.2.1, `domain-gov-policy.md` §8 | `domains/gov_policy/model/`：定义 Task / UrlRecord / FetchRecord 等领域实体；`domains/gov_policy/crawl/`：seed 加载器与派发流程；source seed 使用 `domains/gov_policy/<source>/<source>_seed.yaml`；CLI `scripts/run_crawl_task.py` 把 seed 写入 frontier | `uv run scripts/run_crawl_task.py domains/gov_policy/ndrc/ndrc_seed.yaml` 可派发首批 URL；DB 中可查到 task_spec 与 url_record | `pending` |
| T-20260427-107 | [domains/gov_policy/{crawl,source}] 国务院文件库适配器 | `codegen-output-contract.md` §2, `domain-gov-policy.md` §8 | 在 `domains/gov_policy/<source>/<source>_adapter.py` 写：列表页分页、详情页 URL、DOM 选择器；通用 `crawl` 编排器调用之；下载详情页 HTML + 同页元数据表；附件 PDF 仅落盘 OSS（dev 走本地）；不做 PDF→文本 | 跑 100 条政策，全部原始字节通过 `infra/storage` 落盘；元数据表 + 正文 + 附件清单可被回放查询 | `pending` |
| T-20260427-108 | [domains/gov_policy/{parse} + tests/fixtures] 解析框架 + 国务院黄金用例 | `codegen-output-contract.md` §2.2, §3 | 通用 `parse/` 调度 source adapter hook；输出 `model.PolicyParsed`；`tests/domains/gov_policy/<source>/fixtures/<source>_golden_*` 放固定快照与期望 JSON | 单元测试：5 个黄金用例全绿；解析结果与期望 JSON 一致 | `pending` |
| T-20260427-109 | [domains/gov_policy/dedup] 解析层严格去重 | `data-model.md` §4.2.3 | 联合键 `(policy_title_norm, pub_code, content_sha256)` 一致才去重；不一致全部保留；额外算 simhash64 仅入信号表 | 单元测试：构造转载关系（同 pub_code 同正文 / 同 pub_code 改动正文），验证只去重前者 | `pending` |
| T-20260427-110 | [domains/gov_policy/source-adapters] 8 个国务院部委适配器 | `codegen-output-contract.md` §2 | 复用 §107/§108 模式，在 `domains/gov_policy/{ndrc,miit,mof,nfra,csrc,sasac,pbc,other}/` 各写 `<source>_adapter.py`、`<source>_seed.yaml`，并在 `tests/domains/gov_policy/<source>/fixtures/` 写 `<source>_golden_*` | 每部委跑 50 条，原始页落盘 100% + 黄金用例全绿 + 解析合格率 ≥ 95% | `pending` |
| T-20260427-111 | [infra/ai] LLM 客户端与 prompt 框架 | `codegen-output-contract.md` §6 | `infra/ai/`：通用 LLM 客户端、prompt 模板装载、JSON schema 校验（jsonschema）；只放纯技术能力，不放 36 字段 prompt 文本 | 单元测试：mock 一个 LLM 后端，正反例 schema 校验全部通过 | `pending` |
| T-20260427-112 | [domains/gov_policy/{extract,sink}] 抽取流水线 | `domain-gov-policy.md` §5, `codegen-output-contract.md` §4 | 把 36 字段 prompt 文本放在 `extract/prompts/v1.md`、schema 放在 `extract/schemas/policy_doc_v1.json`（业务事实）；从 store 拉解析后政策文本 → 调 `infra/ai` → 校验 → 通过 `sink` 写 `policy_doc` 表 | 跑 100 条政策，schema 合格率 ≥ 90%，关键 6 字段联合准确率 ≥ 95%（人工抽样 30 条） | `pending` |
| T-20260427-113 | [domains/gov_policy/harness_rules] 业务侧 harness 规则占位 | `codegen-output-contract.md` §5 | 暂留空 stub `harness_rules.py`，定义 `compliance_blocklist`、`field_hit_thresholds` 接口；M3.5 codegen-bootstrap 时由 `infra/harness` 调用 | 占位文件存在；import 不报错；单元测试不覆盖（M3.5 一并验收） | `pending` |
| T-20260427-114 | [docs/eval-test] M3 验收报告 | — | 在 `docs/eval-test/` 写下 retained-vs-candidate 工件：抽样 30 条对照 prompt v1 vs v0（v0 = 仅元数据正则），覆盖关键字段准确率与 schema 合格率 | 工件存在且包含上述指标；Evaluator 签字 `green` | `pending` |

## 4. 边界护栏

- **不做**前端页面、订阅推送、用户态。
- **不做** PDF→文本（TD-001）。
- **不做** 多 worker / 分布式（单进程即可撑 MVP）。
- **不做** simhash 自动合并（TD-003）。
- **不做** 反爬绕过；命中即降速/暂停/人工。
- **不做** 31 省市的适配（M4 单独立项）。
- **不引入** 邮件、完整 OTel/Grafana/Loki（待 TD-002、TD-005 提升）。
- **不做** infra 优化项（增量抓取/checkpoint/DLQ/鲁棒性 fixture/可观测性/版本巡检）。已设计但暂缓，见下表与 tech-debt-tracker。

## 5. 已设计但暂缓的 infra 优化（TODO）

下列任务已完成 spec 设计，但**不在 MVP 范围内**。等 MVP 跑稳后由 Planner
决定何时提升进入活跃。

| 任务（原编号） | 范围 | 关联 spec | tech-debt |
|---|---|---|---|
| T-115（暂缓） | 条件请求 + ETag/Last-Modified（增量抓取） | `infra-resilience.md` §1 | TD-010 |
| T-116（暂缓） | 任务级 checkpoint + pause/resume API | `infra-resilience.md` §2 | TD-010 |
| T-117（暂缓） | 异常分级 + DLQ + 补偿队列 | `infra-resilience.md` §4 | TD-010 |
| T-118（暂缓） | 鲁棒性 fixture（7 个研究报告场景） | research §6 | TD-011 |

## 6. 完成标准

`green` 仅当：

- 第 3 节 13 个任务全部 `completed`
- T-113 工件已存在且 Evaluator 签字 `green`
- `docs/prod-spec/domain-gov-policy.md` §7 中第 1/3/4/5 行指标在 MVP 抽样下达标
- 本文件移到 `docs/exec-plan/archive/2026-W18/`（按合入周）
