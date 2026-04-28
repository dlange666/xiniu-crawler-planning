# 技术债登记

非紧急债务在此登记，必须由 `Planner` 显式提升后才能进入活跃工作。

| ID | 标题 | 来源 | 提出日期 | 风险 | 状态 |
|---|---|---|---|---|---|
| TD-001 | PDF → 文本提取（PyMuPDF/pdfplumber + OCR 兜底） | 用户暂缓 | 2026-04-27 | 中：政策附件大量为 PDF，影响 36 字段抽取召回 | 暂缓 |
| TD-002 | 邮件通知体系（参考 investment-analyzer 的 send_repo_email.py） | 用户暂缓 | 2026-04-27 | 低 | 暂缓 |
| TD-003 | simhash 相似政策自动合并/聚类合并 | 架构决策 | 2026-04-27 | 中：当前仅作信号，需要人工审核 | 暂缓 |
| TD-004 | 引入 Redis/RabbitMQ 做多 worker 协调 | 规模触发 | 2026-04-27 | 低（单进程能撑 MVP→M3） | 待规模触发 |
| TD-005 | 完整可观测体系（Prometheus 拉取端 + Grafana + Alertmanager + OTel Trace + 日志聚合） | 研究报告 §6 | 2026-04-27 | 中 | 公司基础设施就位后启用；MVP 已交付零自建版（observability）；升级仅替换 recorder 一个文件 |
| TD-006 | 任务级 SLA（host 维度 P95、render backlog 阈值） | P2 review | 2026-04-28 | 低 | 待定，运行一段时间后定 |
| TD-007 | 金丝雀阈值参数（M3.5 T-20260428-207 暴露的环境变量） | codegen-bootstrap | 2026-04-28 | 低 | 待定，运行后调 |
| TD-008 | Headless render pool + render backlog 阈值与触发条件 | P7 review | 2026-04-28 | 中：JS 渲染站点会阻断后续数据源覆盖，但过早接入会带来合规与成本风险 | 已补 `infra-render-pool.md` 与 `deferred-plan.md#plan-20260428-render-pool-bootstrap`；M5 或真实 JS shell/backlog 触发后提升 |
| TD-009 | 合规体系：PII 检测、保留 TTL、删除链路、安全日志 6 月、事件应急 | P0 review | 2026-04-28 | 高 | 待性能阶段稳定后立项；C1/C2/C3/C4/C5/C6/C7 |
| TD-010 | infra 韧性：增量抓取（ETag/304）+ checkpoint + DLQ + 补偿队列 | P1 review | 2026-04-28 | 中 | 已 spec 设计于 `infra-resilience.md`；MVP 跑稳后立项；原 T-20260427-115/T-20260427-116/T-20260427-117 |
| TD-011 | 鲁棒性 fixture 集（research §6 7 个非渲染场景） | P5 review | 2026-04-28 | 中 | 已设计；原 T-20260427-118；与 TD-010 一并提升 |
| TD-012 | 站点版本巡检（`infra/version_guard`） | P1 review | 2026-04-28 | 中 | 已 spec 设计于 `infra-resilience.md` §3；codegen 平台稳定后立项；原 T-20260428-211 |
| TD-013 | 可观测性零自建版（recorder + metric_snapshot + cron 告警 + LiteLLM 成本） | P3/P4/P8 | 2026-04-28 | 中 | 已 spec 与 plan 设计；plan 在 `docs/exec-plan/deferred-plan.md`；MVP 跑稳后立项 |
| TD-014 | ~~可视化自建看板~~（已结案） | 用户决策 | 2026-04-28 | — | **结案 2026-04-28**：spec 重构为 `webui.md` rev 2，MVP 实施；OAuth 部分拆出为 TD-018 |
| TD-015 | 主从分布部署 + 自建分发（`infra/dispatch/`，不用 Airflow/Celery） | 用户决策 | 2026-04-28 | 中 | 已 spec 设计于 `infra-deployment.md`；MVP 单进程跑稳后或扩展期（≥ M4）立项 |
| TD-016 | 多 agent 交叉验证（L4，跳过人审增强） | auto-merge-policy review | 2026-04-28 | 中 | spec §8 标注；先用 L1+L3+L6+L8 跑数据，按 false-positive 比例决定是否引入 |
| TD-017 | 独立影子运行（L5） | auto-merge-policy review | 2026-04-28 | 低 | spec §8 标注；tier-2 canary Stage 0 已隐式覆盖；不主动建 |
| TD-018 | webui OAuth/OIDC 接入（Authorization Code + PKCE，authlib，role 由 IdP claims 映射） | 用户决策 | 2026-04-28 | 中：MVP 用 DevBackend 免登在内网受信环境可用；公网或多用户落地前必须切 OAuth | 待公司 IdP 选型确认后立项；spec 契约已写入 `webui.md` §5.4 |
