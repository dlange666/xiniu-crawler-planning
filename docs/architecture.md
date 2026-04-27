# 架构

参考 `docs/research/research-ai-first-crawler-system-20260427.md`（以下简称
"研究报告"）的"控制面 + 数据面"分层模式。本文件定义本仓库当前阶段的**收
敛版**——只描述 MVP→M3 阶段确实会落地的部分，平台化能力（多租户、跨集
群、模型灰度、删除链路）暂作研究报告的 backlog 引用。

## 1. 分层

```
┌──────────────────── Control Plane ────────────────────┐
│ Task API · Policy Engine · Frontier · Lease/Shard      │
└────────────────────────────────────────────────────────┘
            ▲                      │
            │                      ▼
┌──────────────────── Data Plane ────────────────────────┐
│ Fetcher → (Renderer 按需) → Parser → AI Extractor →    │
│ Dedup(解析层) → Sink(PolarDB / OSS)                    │
└────────────────────────────────────────────────────────┘
```

- **控制面**自研：Task API、policy/作用域规则、Frontier 优先级、租约。
- **数据面**复用成熟组件：HTTP 客户端、浏览器自动化、对象存储、检索索引。
- **AI** 不进入主路径：仅在页面分类、内容字段抽取、URL 排序、反爬识别等位置介入。

## 2. Bounded Contexts（落地边界）

| Context | 路径（计划） | 职责 |
|---|---|---|
| `policy_crawl` | `domains/policy_crawl/` | seed 管理、Frontier、host 调度、Fetcher、原始页落盘 |
| `policy_render` | `domains/policy_render/` | headless 渲染池（按需启用；MVP 暂缓） |
| `policy_parse` | `domains/policy_parse/` | 站点适配器、元数据/正文/附件分离、链接抽取 |
| `policy_extract` | `domains/policy_extract/` | AI prompt、36 字段 JSON 生成、schema 校验 |
| `policy_dedup` | `domains/policy_dedup/` | 解析层 `content_sha256` 严格去重 + simhash 信号 |
| `policy_sink` | `domains/policy_sink/` | 写 PolarDB 元数据 + OSS 原始档 |

跨 context 共享的纯技术能力放 `infra/`：
- `infra/http/`：HTTP 客户端、UA、cookie jar、Retry-After/退避
- `infra/robots/`：RFC 9309 实现
- `infra/frontier/`：两级队列、host 礼貌性令牌、任务预算令牌
- `infra/storage/`：SQLite/PolarDB 抽象、OSS 抽象（生产→`oss2`，本地→文件系统适配）
- `infra/observability/`：结构化日志、OTel 埋点（M5 启用）
- `infra/ai/`：LLM 客户端、prompt 模板、JSON schema 校验

## 3. 抓取策略默认顺序

`feed/sitemap → static HTML → 接口拦截（GraphQL / JSON API）→ SSR/DOM → headless 渲染`

进入下一档的触发信号：
- 静态正文显著缺失或选择器命中为空
- 列表页关键链接由 JS 注入
- 网络日志显示 XHR/Fetch 是真正数据源

## 4. 数据形态

| 形态 | 开发/测试 | 生产 |
|---|---|---|
| 元数据库 | SQLite (`runtime/db/dev.db`) | PolarDB |
| 原始页字节 | 本地文件系统 (`runtime/raw/<yyyy>/<mm>/<dd>/`) | 阿里云 OSS |
| 结构化 JSON | SQLite + 本地 JSON | PolarDB + 后续 ES（M6） |
| 临时快照 | `runtime/db/test_*.db` | 不存在 |

存储抽象层（`infra/storage/`）通过环境变量 `STORAGE_PROFILE=dev|prod` 切换实现，业务代码不感知差异。

## 5. 去重策略（重要决策）

- **不在 source 层去重**：抓取链路不做跨 host 比对，避免漏掉"极其相似但有变更"的版本。
- **解析层做严格去重**：以"标题 + 发文字号 + 正文 SHA256"为联合键；联合键完全相等才去重。
- **simhash 仅作信号**：相似度高于阈值的不同记录写入 `policy_similar_cluster` 表，供后续人工审核或 AI 复核。

## 6. 反爬与合规执行点

- robots 在 Frontier 入口预取，命中拒绝直接终止该 URL 派发
- 命中 challenge / captcha / WAF block / auth required → host 进入 cooldown，记录人工审核工单，**不重试**
- IP/代理只用于"出口稳定性 + 路由控制"，不用于对抗保护措施

## 7. 与研究报告的差异

- 不上 etcd/Kafka 等中间件：MVP 阶段单进程 + SQLite 即可；扩到多 worker 时再引入 Redis/RabbitMQ
- 不做 PDF→文本（用户暂缓决定）
- 不接入邮件通知（用户决定）
- 不做 simhash 自动合并（用户决定）
- 不做 multi-tenant、删除链路、模型灰度（推迟到平台化阶段）
