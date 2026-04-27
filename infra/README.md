# infra/

跨业务域复用的**纯技术能力**。**不得**包含任何业务规则（如政策行业分
类、字段语义判断、政府发文层级判定）。这些都属于 `domains/<context>/`。

判定 "属于 infra 还是 domain" 的简单准则：

- 这段逻辑能被另一个业务域（如 `exchange_policy`）原样复用吗？
  - 是 → `infra/`
  - 否 → `domains/<context>/`

## 计划模块（按 MVP 计划顺序建设）

| 模块 | 状态 | 职责 | 建设任务 |
|---|---|---|---|
| `storage/` | 待建 | `MetadataStore`/`BlobStore` 协议；SQLite/PolarDB/LocalFS/OSS 实现；`STORAGE_PROFILE` 切换 | T-20260427-102 |
| `http/` | 待建 | HTTP 客户端、UA、cookie jar、Retry-After/退避、host 令牌桶 | T-20260427-103 |
| `robots/` | 待建 | RFC 9309 实现、24h 缓存、5xx → complete disallow | T-20260427-104 |
| `frontier/` | 待建 | 单进程两级队列（全局优先级堆 + per-host ready queue）、三类令牌 | T-20260427-105 |
| `ai/` | 待建 | LLM 客户端、prompt 模板装载器、JSON schema 校验（不放具体业务 prompt 文本） | T-20260427-111 |
| `observability/` | 推迟 | 结构化日志、OTel 埋点 | M5（TD-005） |

## 反向依赖禁令

`infra/*` 不得 import `domains/*`。CI 应在后续阶段加 import-linter 守护。
