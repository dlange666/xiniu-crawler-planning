# docs/prd/ —— 产品需求文档归档

收录**来自外部（产品方、业务方、合规、客户）**的原始需求文档。docx → md
转写归档，不再演进。需要工程化的内容应当被吸收到 `docs/prod-spec/` 下的
正式 spec 中。

> 工程团队自己写的研究/设计提案放 `docs/research/`，不在本目录。

## 命名约定

- `<topic>-<sub-topic>-YYYYMMDD.md`：日期后缀作为收件日期
- 文件名应能反映"原始 docx 主题"，便于回溯出处

## 索引

| 文件 | 内容 | 来源 | 关联 prod-spec |
|---|---|---|---|
| `policy-graph-product-plan-20260427.md` | 政策图谱产品策划（用户、价值、36 字段定义、AI 解读模板） | 产品同事 docx | `domain-gov-policy.md` |
| `policy-data-sources-phase1-20260427.md` | 第一阶段政策采集源说明（中央 + 8 部委 + 31 省市，105+ URL） | 产品同事 docx | `domain-gov-policy.md` |

## 何时新增

- 产品方给 docx 描述新业务域 / 新需求
- 业务方给的字段定义、数据源清单、合规要求
- 合规/法务发的政策、SOP

## 何时不新增

- 工程团队自己写的设计/调研 → 放 `docs/research/`
- 临时口头需求或微信对话 → 不入仓库；正式化后再来归档
- 已被规格化的内容如果原稿已废 → 由 `Cleaner` 评估后清理，避免长期信息冗余
