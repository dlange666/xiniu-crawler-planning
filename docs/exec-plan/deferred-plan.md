# 暂缓计划（Deferred Plans）

收录"已完成详细设计但暂不实施"的 plan。每个 plan 一个二级章节；何时启用
由 `Planner` 显式决定。

## 与 `tech-debt-tracker.md` 的区别

| 文档 | 内容粒度 | 何时用 |
|---|---|---|
| `tech-debt-tracker.md` | 1 行登记（标题 + 风险 + 状态） | 还没做完整设计的债务 |
| 本文件章节 | 完整 plan（任务列表 + 验收 + 边界） | **设计已经做完**但用户决定暂不实施 |

提升流程：本文件中某节内容整体提升 → 复制到 `active/plan-<date>-<slug>.md`
→ 本文件该节删除 + cleanup-log 记录 + tech-debt 对应 TD 升级。

---

## plan-20260428-observability-bootstrap

### 元信息

- **Plan ID**：`plan-20260428-observability-bootstrap`
- **关联规格**：`docs/prod-spec/infra-observability.md`（零自建后台版）、`docs/prod-spec/infra-resilience.md`
- **状态**：`deferred`（不进入 MVP；MVP 跑稳后由 Planner 决定何时提升）。登记 TD-013
- **里程碑**：M-Observability（≈1.5 周）

### 目标

交付**零自建后台服务**的最小可观测性：所有指标存到与业务同一个 DB，
告警靠 cron + SQL + IM webhook，无 Prometheus / Alertmanager / Grafana。
后续公司基础设施就位（TD-005），仅替换 `recorder.py` 一个文件即可升级。

### 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式 | 状态 |
|---|---|---|---|---|---|
| T-20260428-301 | [infra/observability] recorder + snapshot flusher | `infra-observability.md` §3, §4 | `infra/observability/recorder.py` 提供 `incr/observe/set` API（接口与 prometheus-client 兼容）；进程内聚合；每 60s flush 到 `metric_snapshot` 表（按 `infra-observability.md` §3）；按 §4 注册 8 个采集负载指标；与 frontier、http、parse hook 点连接 | 单元测试：跑 fake 任务后查表得到 8 个指标；recorder 接口签名与 prometheus-client 等价 | `pending` |
| T-20260428-302 | [scripts] OSS 用量轮询 | `infra-observability.md` §5 | `scripts/observe_oss_usage.py`：调阿里云 OSS API 按 `infra-observability.md` §5 写入 4 个指标到 metric_snapshot；外部 cron 每小时触发；月成本估算公式从配置读 | 单元测试：mock OSS 响应；月成本与字节数同方向；运行后 metric_snapshot 有对应行 | `pending` |
| T-20260428-303 | [infra/ai] LiteLLM gateway 接入 + 成本指标 | `infra-observability.md` §6 | `infra/ai/llm_client.py` 默认走 LiteLLM（OpenAI 兼容协议指向 `LITELLM_BASE_URL`），透传 `x-litellm-tags=task=...,context=...`；`scripts/observe_llm_spend.py` 每 10min 调 `/spend/get` 写入 6 个指标；预算守门按 §6 三档生效（剩余 < 20%/5%/0%） | 单元测试：mock LiteLLM；标签透传正确；预算三档行为正确；指标写表 | `pending` |
| T-20260428-304 | [scripts] 告警脚本 + IM webhook | `infra-observability.md` §7 | `scripts/observe_check.py`：按 `infra-observability.md` §7 跑 8 条告警 SQL；命中即 POST 到 `OBSERVE_WEBHOOK_URL`（钉钉/飞书/企微）；payload 格式见 §7；外部 cron 每 5min 触发 | 单元测试：注入超阈值数据 → webhook 收到正确 payload；空数据不触发；webhook 故障不影响主流程 | `pending` |
| T-20260428-305 | [docs/eval-test] M-Observability 验收 | — | 用一个跑 24h 的小流量任务作为基线；查询 metric_snapshot 与告警历史；写入 `docs/eval-test/` 报告 | 工件含 18 个指标的真实数值 + 至少一次告警 webhook 投递记录 | `pending` |

### 边界护栏

- **不部署** Prometheus / VictoriaMetrics / Alertmanager / Grafana / Loki。
- **不暴露** `/metrics` HTTP endpoint（升级时再加）。
- **不引入**新的 LLM 客户端实现路径；执行面 LLM 调用统一走 LiteLLM gateway。
- **不绕过** LiteLLM 后台预算；提权走 LiteLLM 后台。
- **不让** webhook 故障影响止损：所有自动止损动作（暂停 host、disable adapter）由进程内 frontier/anti-bot 直接触发，与 webhook 链路解耦。

### 完成标准（提升后启用）

`green` 仅当：

- 第 3 节 5 个任务全部 `completed`
- T-305 工件展示 18 个指标在 24h 真实样本下有数值
- LiteLLM 后台已配置至少一个 `business_context` 的月度预算
- 至少一次告警 webhook 端到端跑通（钉钉/飞书/企微任一）

### 后续升级路径（不在本 plan 内）

公司有 Prometheus 拉取端后：

1. 在 `recorder.py` 加 `PrometheusBackend`，与 `DBSnapshotBackend` 并存（环境变量切换）
2. 暴露 `/metrics`，运维加 scrape config
3. cron+SQL 告警渐进迁移到 PrometheusRule
4. `metric_snapshot` 表保留 90d 后退役

升级期间业务代码完全不动。
