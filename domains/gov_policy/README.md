# domains/gov_policy

**业务域：政府产业政策**

聚焦中央行政机关、国务院部委、31 省市自治区政府门户发布的产业政策。规格
见 `docs/prod-spec/policy-graph-v1.md`。

## 子模块布局

| 子模块 | 路径 | 职责 |
|---|---|---|
| `model/` | 业务实体 | `Task`、`UrlRecord`、`FetchRecord`、`PolicyParsed`、`PolicyDocJSON`、`Attachment`、`SourceMetadata` 等纯数据结构与领域规则 |
| `crawl/` | 采集编排 | seed 加载、调用 `infra/frontier` 派发、调用 `infra/http` 抓取、原始字节交 `sink` |
| `render/` | 按需渲染 | headless 渲染编排（M5 启用，MVP 只占位） |
| `parse/` | 站点解析 | 站点适配器（国务院 / 各部委 / 各地方），元数据/正文/附件三段分离，链接抽取 |
| `dedup/` | 解析层去重 | 联合键严格去重 + simhash 信号 |
| `extract/` | AI 抽取 | 36 字段 prompt + JSON schema + 调 `infra/ai` 跑抽取 |
| `sink/` | 写入 | 通过 `infra/storage` 写 PolarDB 元数据 + OSS 原始档 |
| `seeds/` | 数据源 | seed YAML 清单 |

## 子模块依赖方向

```
crawl → frontier(infra), http(infra), robots(infra), model, sink
parse → model, dedup, sink
dedup → model
extract → model, ai(infra), sink
sink → storage(infra), model
```

子模块之间通过 `model` 提供的纯数据结构通信；不持有彼此的内部实现。
