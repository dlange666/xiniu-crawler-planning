# 政策图谱 v1 产品规格

> 本文件是爬虫仓库视角的**业务规格**。完整产品策划请见
> `docs/research/policy-graph-product-plan-20260427.md`。本文件只描述爬虫
> 仓库需要交付的部分：采集对象、采集层级、字段定义、验收门槛。

## 1. 业务目标

聚合**全国各地发布的产业政策**，对每条政策做深度结构化处理，输出可被检
索、解读、统计、对比、推送的标准 JSON 数据集。

爬虫仓库交付：稳定、可回放、可审计的政策数据集 + 标准 36 字段 JSON。

## 2. 第一阶段采集范围

| 类别 | 来源 | 说明 |
|---|---|---|
| 法律法规 | 国家法律法规数据库（`flk.npc.gov.cn`） | 仅作引用跳转，**不打标签** |
| 中央行政机关 | 国务院政策文件库 + 国务院要闻 | 政策、政策解读、规章、新闻要闻 |
| 国务院部委 | 国家发改委、工信部、财政部、国家金融监督管理总局、证监会、国资委、人民银行、其他 | 8 类，按各部委导航分类逐一爬取 |
| 地方行政机关 | 31 省市自治区政府门户的"信息公开 + 要闻 + 政策解读"三类入口 | 共约 90 个 URL |
| 金融交易所、行业协会 | 见 `docs/research/policy-data-sources-phase1-20260427.md` 详细清单 | 第一阶段后期补齐 |

完整 URL 清单与可爬取元数据列表见研究底稿
`docs/research/policy-data-sources-phase1-20260427.md`。

## 3. 数据形态

每条政策网页通常由三部分组成，**全部需要采集**：

1. **元数据表格**（文本，由网页本身标注的属性表）
2. **正文**（文本）
3. **附件**（PDF；本期不做 PDF→文本，仅落盘原始字节，见技术债 TD-001）

源站元数据需要与正文存放在同一档案下，供 AI 抽取时参考。

## 4. 数据种类

按研究底稿，政策被分为 6 种数据种类（其中 1 类不打标签）：

| 数据种类 | 说明 | 是否打标签 |
|---|---|---|
| 法律法规 | 仅作跳转引用 | 否 |
| 政策（含通知公告） | 行政规范性文件、政策指导、试点文件 | 是 |
| 政策解读 | 政策的官方解释，挂钩主政策 | 是 |
| 规章 | 部门或地方政府制定的规则性文件 | 是 |
| 规划信息 | 国家/地方/行业发展规划 | 是 |
| 新闻要闻 | 新闻发布、媒体报道、官方要闻 | 是 |

## 5. 标签 36 字段（AI 结构化输出）

完整 prompt 与字段说明见 `docs/research/policy-graph-product-plan-20260427.md`
§3.1.2。本规格只列字段名与类型，作为入库 schema 与验收依据。

### 5.1 元数据字段（15 个）

| 字段 | 类型 | 说明 |
|---|---|---|
| `policy_title` | str | 完整标题 |
| `pub_date` | date | 发布日期（YYYY-MM-DD） |
| `valid_date` | date | 生效日期 |
| `invalid_date` | date | 废止日期 |
| `pub_code` | str | 发文字号 |
| `pub_organization` | str | 发布机关 |
| `pub_org_level` | enum | 国家级 / 省级 / 地市级 / 区县级 / 乡级 |
| `pub_region_level1` | str | 一级行政区划 |
| `pub_region_level2` | str | 二级行政区划 |
| `pub_region_level3` | str | 三级行政区划 |
| `policy_category` | enum | 政策 / 政策解读 / 规章 / 规划信息 / 通知公告 / 新闻要闻 |
| `plan_period` | enum | 十二五 / 十三五 / 十四五 / 十五五 / 十六五 |
| `policy_tool_type_level1` | enum | 规制类 / 激励类 / 服务类 / 引导类 / 纾困类 / 考核类 |
| `policy_tool_type_level2` | enum | 二级工具分类（如财政补贴、税收优惠等） |
| `policy_goal_type` | enum | 经济发展类 / 社会民生类 / 生态文明类 / 国家安全类 / 科技创新类 |

### 5.2 实体内容字段（9 个）

| 字段 | 类型 | 说明 |
|---|---|---|
| `policy_keywords` | text | 5–10 个核心关键词 |
| `policy_summary` | text | 100–500 字摘要 |
| `policy_apply_objects` | text | 适用对象 |
| `policy_directory` | text | 多级标题，分号分隔 |
| `policy_included_industries` | text | 直接提到的产业 |
| `policy_included_terms` | text | 政策专有名词 |
| `term_explain` | text | 名词解释（"名词：释义"分号分隔） |
| `related_policy_title` | text | 关联政策标题 |
| `reference_original_text` | text | 关联政策的原文依据 |

### 5.3 行业影响分析字段（12 个）

按 4 套行业体系（烯牛行业、国民经济行业、战略新兴产业、一二级互通行业）
各 3 字段：`*_label`、`*_evidence`、`*_sentiment`。

| 字段 | 类型 |
|---|---|
| `xiniu_industry_label` / `xiniu_evidence` / `xiniu_sentiment` | text |
| `national_economy_label` / `national_economy_evidence` / `national_economy_sentiment` | text |
| `strategic_emerging_label` / `strategic_emerging_evidence` / `strategic_emerging_sentiment` | text |
| `primary_secondary_label` / `primary_secondary_evidence` / `primary_secondary_sentiment` | text |

## 6. 采集流程约束

1. 先爬中央行政机关，再扩部委，再扩地方。
2. 由于其他部门会**转载**国务院文件，需保留"极其相似但有变更"的版本；**仅去重内容百分百一致**的副本。
3. 去重在解析层做（`policy_title + pub_code + content_sha256` 联合键严格匹配）；source 层不做去重。
4. PDF 附件本期仅原始落盘，不入文本（TD-001）。
5. 全程遵守 `AGENTS.md` 中的爬虫硬规则（不绕过保护、robots、Retry-After、原始页留存等）。

## 7. 成功标准（爬虫侧）

| 维度 | 指标 | v1 门槛 |
|---|---|---|
| 覆盖 | 第一阶段已配置数据源数 | ≥ 105 入口 |
| 鲜度 | 新政策从发布到入库 P95 | < 24h |
| 保真 | 原始页可回放比例 | = 100% |
| 解析 | AI 输出 36 字段 JSON schema 合格率 | ≥ 90% |
| 关键字段 | 标题/发文字号/发布日期/发文层级/行政区划/政策种类的 6 项联合准确率 | ≥ 95% |
| 礼貌 | host 维度 429/5xx 比例 | < 1% |
| 合规 | robots / 反爬命中后未尝试绕过 | = 100% |

## 8. 不在 v1 范围

- 前端检索/解读/统计/对比/推送页面（产品同学规划，非本仓库交付）
- PDF → 文本（TD-001）
- simhash 相似政策自动合并（TD-003）
- 跨境/海外站点
- 多租户、订阅推送、删除链路平台化能力（推迟到平台化阶段）
