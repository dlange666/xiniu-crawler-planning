# docs/research/ —— 研究底稿索引

仅放**工程视角的研究与设计提案**——调研、技术对比、跨日设计稿。每份是
历史快照，归档后仅修改错别字，不再演进。需要演进的内容应当转化为
`docs/prod-spec/` 下的正式 spec。

> 业务/产品方给的原始需求文档（PRD、数据源清单等）放 `docs/prd/`，不在本目录。

## 命名约定

- `<topic>-<sub-topic>-YYYYMMDD.md`：日期后缀作为身份标记
- 不强制前缀分组（数量少；演进态在 prod-spec）

## 索引

| 文件 | 内容 | 关联 prod-spec |
|---|---|---|
| `research-ai-first-crawler-system-20260427.md` | AI-First 通用爬虫总体架构研究（28 周里程碑、控制面/数据面分层、AI 决策栈、研究报告原稿） | `architecture.md` 与 `infra-*` 整体设计的源头依据 |
| `design-task-driven-codegen-20260427.md` | 任务驱动代码生成系统设计提案（双平面、状态机、prompt 框架） | `codegen-output-contract.md`、`codegen-auto-merge.md` |

## 何时新增

- 大型设计提案（影响多个 spec / domains 边界）
- 跨周期回顾或风险评估
- 选型对比、技术评估

## 何时不新增

- 小幅设计调整 → 直接改 prod-spec + 修订历史
- 单点决策记录 → 写到 cleanup-log 或 task 文件
- 临时讨论纪要 → 不入仓库
- 来自产品/业务方的原稿 → 放 `docs/prd/`
