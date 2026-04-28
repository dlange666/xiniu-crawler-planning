# 清理日志

记录工作流维度的清理动作（过期分支、未引用文档、临时 DB 等）。
新条目追加到顶部。

| 日期 | 范围 | 动作 | 操作者 |
|---|---|---|---|
| 2026-04-28 | 删 exec-plan/completed/ legacy 空目录 | 该目录是从 investment-analyzer 模板继承下来的兼容层，新 plan 走 archive/YYYY-Www/。删除目录；index.md 同步去掉相关说明 | Cleaner |
| 2026-04-28 | 删除冗余 docs/index.md | 内容已被 AGENTS.md Repository Map / Doc Naming Conventions + 根 README.md "Start Here" 覆盖；docs 根目录不需要二级索引。子目录 index.md 保留 | Cleaner |
| 2026-04-28 | 删除冗余"门牌"文件 | 删 `docs/domains-overview.md` / `docs/domain-gov-policy-layout.md` / `docs/infra-overview.md`：内容已被 `architecture.md`（§2 目录结构 + §2.1 Capability×Spec×Plan）+ `prod-spec/index.md` + `prod-spec/domain-gov-policy.md` §8 完整覆盖；AGENTS.md / README.md / docs/index.md / 受影响 spec 与 plan / design 提案的引用同步更新 | Cleaner |
| 2026-04-28 | SDD 视角加固 P0+P1+P2 | (P0-1) `design-task-driven-codegen` 顶部加 ⚠️ superseded banner + 文末加"取代关系"对照表；(P0-2) plan 任务表加 `spec_ref` 列（template + 3 份 plan：mvp / codegen-bootstrap / deferred-plan，共 33 个任务全部填充）；(P0-3) `eval-test/template.md` 加 `validates: <spec>.md §<n>` 行；(P1) `architecture.md` §2.1 新增 Capability × Spec × Plan × 代码落点 9 行对照表；(P2) AGENTS.md `Spec Versioning` 加 2 条硬规则：代码 PR 与 spec 修订同 PR；取代关系标注规范 | Planner |
| 2026-04-28 | PRD 与 research 分离 | 新建 `docs/prd/`：产品/业务方原稿归档（`policy-graph-product-plan-20260427.md`、`policy-data-sources-phase1-20260427.md` 从 research 移过来）；`docs/research/index.md` 改写边界（仅工程视角研究/设计提案）；AGENTS.md Repository Map + Doc Naming Conventions + index.md 名单更新 | Cleaner |
| 2026-04-28 | 暂缓 plan 收口 | 删除 `docs/exec-plan/deferred/` 子目录，内容合并为顶层 `deferred-plan.md`（章节式）；index.md 与 tech-debt-tracker 引用同步更新 | Cleaner |
| 2026-04-28 | 文件名 lowercase 统一 | `PLAN-*` / `ROADMAP-*` 改 `plan-*` / `roadmap-*`（4 份文件重命名）；Plan ID 字符串同步小写；AGENTS.md `Doc Naming Conventions` 加"kebab-case + lowercase"强约束 | Cleaner |
| 2026-04-28 | 文档目录索引收口 + 业务 spec 加 domain- 前缀 | `policy-graph.md` → `domain-gov-policy.md`；`gov-policy-layout.md` → `domain-gov-policy-layout.md`；4 个目录索引以 `index.md` 命名（`docs/`、`docs/prod-spec/`、`docs/research/`、`docs/exec-plan/`），保留根 `README.md` 唯一项目入口；AGENTS.md 新增 `Doc Naming Conventions` 节统一描述 5 类前缀分组 | Cleaner |
| 2026-04-28 | 移除 experiment 工作流 | 删除 `docs/experiment/`、`skills/crawler-workflow-experiment/`；AGENTS.md `Operating Flows` 去掉 Experiment Flow 节、Repository Map 与 docs lifecycle 列表去掉 experiment；`crawler-workflow` 路由 4 → 3 项；`crawler-workflow-execution` 模板列表 5 → 4 项；`docs/eval-test/template.md` 类型去掉 experiment-artifact，改为 acceptance/regression/adversarial/ad-hoc | Cleaner |
| 2026-04-28 | prod-spec 命名收敛 | `observability.md` → `infra-observability.md`；`auto-merge-policy.md` → `codegen-auto-merge.md`；新建 `docs/prod-spec/README.md` 作为索引；AGENTS.md `Spec Versioning` 加命名约定（业务/infra-/codegen-/单名 4 类） | Cleaner |
| 2026-04-28 | 数据模型集中化 | 新建 `data-model.md`（21 张表统一 DDL 权威源；最小化 JSON）；重构 `crawl_task` 单表 → 4 张表（task / generation / execution / run）+ 3 子表 + 1 审计；`codegen-output-contract.md` rev 2、`infra-deployment.md` rev 3、design 提案 §3 全部改为引用 data-model.md，避免双源不一致 | Planner |
| 2026-04-28 | 跳过人审安全网 | 新建 `codegen-auto-merge.md`（tier 1/2/3 分级 + 加压 harness + 4 档渐进 canary + 自动回滚 + IM 审计）；`infra-fetch-policy.md` rev 2 加 §2.3 限流分级启动 warm-up；codegen 设计提案状态机扩为 canary_stage_0/1/2/3 + rolled_back；M3.5 plan 加 T-212~216；TD-016/017 登记 L4/L5 后续优化 | Planner |
| 2026-04-28 | 借鉴上一版 OpenCode 实现 | 新建 `codegen-output-contract.md`（adapter 架构 + 默认 sink schema + harness 门槛 + prompt 拆分）；`infra-resilience.md` rev 2 加 §2.5 心跳与卡死恢复；`infra-deployment.md` rev 2 加 §3.4 SKIP LOCKED 与 master_lease SQL；codegen 设计提案 task 模型加 scope/crawl_mode/crawl_until/full_crawl_cron/heartbeat_at | Planner |
| 2026-04-28 | spec 版本治理 | 6 份 spec 去 `-v1` 后缀；统一 frontmatter（rev / 最近修订 / 状态）+ `## 修订历史`；新建 `docs/prod-spec/template.md`、`docs/eval-test/template.md`；AGENTS.md 加 Spec Versioning 硬规则；crawler-workflow / execution skill 加 spec 编辑前置检查 | Planner |
| 2026-04-28 | README 归档 | `domains/README.md` → `docs/domains-overview.md`；`domains/gov_policy/README.md` → `docs/domain-gov-policy-layout.md`；`infra/README.md` → `docs/infra-overview.md`。仓库只保留顶层 `README.md` | Cleaner |
| 2026-04-27 | 仓库初始化 | 创建控制面骨架，未做清理 | Planner |
