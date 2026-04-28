# domains/gov_policy

**业务域：政府产业政策**

聚焦中央行政机关、国务院部委、31 省市自治区政府门户发布的产业政策。规格
见 `docs/prod-spec/policy-graph.md`。

## 子模块布局

| 子模块 | 路径 | 职责 |
|---|---|---|
| `model/` | 业务实体 | `UrlRecord`、`FetchRecord`、`PolicyParsed`、`PolicyDocJSON`、`Attachment`、`SourceMetadata` 等纯数据结构与领域规则 |
| `crawl/` | 采集编排 | 通用 seed 加载、调用 `infra/frontier` 派发、调用 `infra/http` 抓取、把原始字节交 `sink` |
| `render/` | 按需渲染 | headless 渲染编排（M5 启用，MVP 占位） |
| `parse/` | 解析框架 | 通用解析流程：调度对应 `adapters/<host>` 的 hook，做元数据/正文/附件分离与链接抽取 |
| `adapters/` | 站点适配器 | 每个 host 一个文件 `adapters/<host>.py`：列表页/详情页 URL 模式、DOM 选择器、解析 hook。MVP 由人手写，M3.5 起由 codegen 产出 |
| `golden/` | 黄金用例 | 每 host 一组固定快照与期望 JSON：`golden/<host>/*.html` + `*.golden.json`。harness 据此跑单元校验 |
| `seeds/` | 数据源 | YAML 列出每个 host 的入口 URL、抓取频率、礼貌性参数 |
| `dedup/` | 解析层去重 | 联合键严格去重 + simhash 信号 |
| `extract/` | AI 抽取 | 36 字段 `prompts/` + `schemas/` + 调 `infra/ai` 跑抽取 |
| `sink/` | 写入 | 通过 `infra/storage` 写元数据 + 原始档 |
| `harness_rules.py` | 业务侧 harness 规则 | 注入 `infra/harness/` 的字段命中率门槛、合规扫描禁词补充等 |

## 子模块依赖方向

```
crawl   → infra/{frontier,http,robots,storage} · model · adapters · sink
parse   → adapters · model · dedup · sink
adapters→ model（仅纯函数 hook，不持有 infra）
dedup   → model
extract → infra/ai · model · sink
sink    → infra/storage · model
```

子模块之间通过 `model` 提供的纯数据结构通信；不持有彼此的内部实现。
`adapters/<host>.py` 是站点适配器的唯一栖身地——既不嵌套在 `parse/sites/`
下，也不在仓库顶层独立——保持深度浅且紧贴业务域。
