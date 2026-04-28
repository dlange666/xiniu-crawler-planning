# 政策爬虫总路线图

> 本文是**长期路线图视图**。当前活跃计划是 `PLAN-20260427-mvp-policy-crawler.md`
> （MVP / M0–M3）。M4 起的子计划在前一阶段关闭时再创建。

对应研究报告 `docs/research/research-ai-first-crawler-system-20260427.md` §7
的 28 周里程碑。每个里程碑都对齐"可上线、可验收、可回滚"。

| 阶段 | 里程碑 | 周期 | 范围 | 关键验收 |
|---|---|---|---|---|
| MVP | M0 项目骨架 | 0.5 周 | 控制面 + workflow + 技术选型 | 仓库可被 crawler-workflow 驱动 |
| MVP | M1 单源跑通 | 2 周 | 国务院文件库静态抓取 + 元数据/正文/附件分离 + 原始页可回放 | 100 条全量字节落盘 |
| MVP | M2 多源 + 解析层去重 | 3 周 | 8 个国务院部委 + 严格去重 | 转载政策只留 1 条；改动版均保留 |
| MVP | M3 AI 结构化 | 3 周 | 36 字段 prompt → JSON 校验 → 入库 | schema 合格率 ≥ 90%、关键 6 字段准确率 ≥ 95% |
| ~~平台~~ | ~~M-Observability~~ | ~~1.5 周~~ | **暂缓**（plan 移至 `docs/exec-plan/deferred/`，TD-013） | — |
| 平台 | M3.5 Codegen Bootstrap | 3 周 | `infra/{agent,sandbox,harness,codegen,adapter_registry,scheduler}` + 端到端复刻部委验收（**不含**版本巡检 `version_guard`，TD-012） | OpenCode 自动产出 1 个适配器并通过 harness、人审、合并 |
| 扩展 | M4 地方政府全覆盖 | 4 周 | 31 省市"信息公开 + 要闻 + 政策解读"三入口；M4 起新适配器**优先由 codegen 产出** | 数据源数 ≥ 105；任务级 SLA；codegen 产出占比 ≥ 70% |
| 扩展 | M5 调度 + 反爬 + 渲染 | 4 周 | 两级队列扩多 worker + 429/503 处理 + headless 渲染池（按需） | 反爬命中场景不失控 |
| 优化 | M6 可观测性 | 3 周 | OTel + Grafana + Alertmanager + 回放工具 | 任务/调度/AI 主面板齐备 |
| 平台化 | M7 检索 + 多租户 + 配额 | 4 周 | ES 检索、租户隔离、审计 | 第二个业务方可接入 |
| 平台化 | M8 成本治理 + 模型灰度 + 删除链路 | 4 周 | 模型可灰度、删除工单闭环、成本可归因 | 满足合规与持续降本 |

## 阶段间过渡条件

- M1 → M2：原始页落盘比例 = 100%、回放命令可重现单条政策
- M2 → M3：解析合格率 ≥ 95%、跨部委转载去重生效
- M3 → M3.5：MVP plan 全部 green；至少 9 个手写适配器（国务院 + 8 部委）已合并，作为 codegen few-shot 模板
- M3.5 → M4：codegen 端到端复刻部委验收 green；外部 task 项目接口已对齐
- M4 → M5：105+ 入口活跃；出现 host 维度 429/5xx 显著上升
- M5 → M6：渲染池稳定运行 ≥ 2 周；7 天 P95 时延 < 24h
- M6 → 平台化：观测口径满足生产，外部业务方提出接入
