# docs/research/ —— 研究底稿索引

研究类文档**自由格式**，没有强制模板。每份是某次调研/设计提案的**历史快
照**，归档后仅修改错别字，不再演进。需要演进的内容应当转化为
`docs/prod-spec/` 下的正式 spec。

## 命名约定

- `<topic>-<sub-topic>-YYYYMMDD.md`：日期后缀作为身份标记
- 不强制前缀分组（数量少；演进态在 prod-spec）

## 索引

| 文件 | 内容 | 关联 prod-spec |
|---|---|---|
| `research-ai-first-crawler-system-20260427.md` | AI-First 通用爬虫总体架构研究（28 周里程碑、控制面/数据面分层、AI 决策栈、研究报告原稿） | `architecture.md` 与 `infra-*` 整体设计的源头依据 |
| `policy-graph-product-plan-20260427.md` | 政策图谱产品策划（用户、价值、36 字段定义、AI 解读模板） | `prod-spec/domain-gov-policy.md` |
| `policy-data-sources-phase1-20260427.md` | 第一阶段政策采集源说明（中央 + 8 部委 + 31 省市，105+ URL） | `prod-spec/domain-gov-policy.md` |
| `design-task-driven-codegen-20260427.md` | 任务驱动代码生成系统设计提案（双平面、状态机、prompt 框架） | `prod-spec/codegen-output-contract.md`、`codegen-auto-merge.md` |

## 何时新增

- 大型设计提案（影响多个 spec / domains 边界）
- 跨周期回顾或风险评估
- 来自外部资料（如产品同事的 docx）的转写存档

## 何时不新增

- 小幅设计调整 → 直接改 prod-spec + 修订历史
- 单点决策记录 → 写到 cleanup-log 或 task 文件
- 临时讨论纪要 → 不入仓库
