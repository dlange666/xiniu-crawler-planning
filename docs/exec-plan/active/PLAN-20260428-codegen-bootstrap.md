# PLAN-20260428-codegen-bootstrap

## 1. 元信息

- **Plan ID**：`PLAN-20260428-CODEGEN-BOOTSTRAP`
- **关联规格**：`docs/research/design-task-driven-codegen-20260427.md`（提案）+ 后续转入 `docs/prod-spec/codegen-platform.md`（M3.5 启动时落地）
- **状态**：`active`（依赖 `PLAN-20260427-MVP-POLICY-CRAWLER` 关闭后启动）
- **负责角色**：`Planner`
- **里程碑**：M3.5（≈3 周）

## 2. 目标

建设跨业务域复用的 **codegen 平台**（全部进 `infra/`），让外部独立项目提
交的 task 能驱动本仓库自动产出站点适配器。MVP 阶段产出 1 个端到端可用的
样例任务（如"复刻已存在的部委"）作为验收。

**Task API / Task Store 不在本仓库**——它们在独立的外部项目中维护。本计
划仅建设"消费端"：从外部项目拉 task → 跑 codegen → 提 PR。

## 3. 原子任务列表

| 任务 ID | 标题 | 实现细节 | 验证方式 | 状态 |
|---|---|---|---|---|
| T-20260428-201 | [infra/agent] CodingAgentBackend 抽象与 OpenCode 实现 | 定义 `CodingAgentBackend` 协议；实现 `OpenCodeBackend`（`subprocess` 调 `opencode run`，模型为参数）、`MockBackend`；不内嵌业务 prompt | 单元测试：MockBackend 返回模拟结果；OpenCodeBackend 在本机装好 opencode 时跑通 hello-world prompt | `pending` |
| T-20260428-202 | [infra/sandbox] worktree + 文件系统白名单 | 创建/销毁 git worktree；用 chroot 类机制或显式路径校验把子进程可写路径限制在白名单 | 单元测试：尝试写白名单外路径被拒；尝试写白名单内路径成功 | `pending` |
| T-20260428-203 | [infra/harness] 验证 harness 框架 | 跑 ruff/mypy/import-linter；跑 pytest（业务域提供 golden）；跑 e2e（业务域提供 schema 与门槛）；合规扫描禁词（基线 + 业务域追加） | 单元测试：注入一个合规失败的 fake adapter，harness 拦截并返回 `failed` | `pending` |
| T-20260428-204 | [infra/codegen] codegen worker 主循环 | 从外部 task 源（HTTP poll，接口形态待外部项目敲定）取 `pending` task → 抢锁 → 调 sandbox 建 worktree → 调 agent → 调 harness → `gh pr create`；`task_type=create/update/extend` 三种分支处理；失败 attempts++（≤3） | 端到端：用 MockBackend 跑通一个完整任务，PR 创建于 fork 仓库 | `pending` |
| T-20260428-205 | [infra/codegen] task 接入接口（消费端） | 定义 `TaskSource` 协议：`fetch_pending() / claim() / report_status() / submit_pr()`；提供 `HttpTaskSource` 模板；提供 `LocalFileTaskSource`（dev/测试用，从 YAML 读 task） | 单元测试：LocalFileTaskSource 解析 5 条 task；mock HTTP 跑一次 fetch | `pending` |
| T-20260428-206 | [infra/adapter_registry] 入口点扫描注册 | 启动时扫描 `domains/<context>/adapters/*.py`，按 `(host, data_kind, version)` 注册；提供 `resolve(host, data_kind)` API | 单元测试：3 个 fake adapter 注册并 resolve 正确 | `pending` |
| T-20260428-207 | [infra/scheduler] 定时调度 + 金丝雀池 | cron 触发已注册 adapter；新合入 adapter 先进金丝雀池（独立 sink table、低 RPS）；金丝雀策略阈值待定，先用环境变量参数化 | 单元测试：fake adapter 调度命中；金丝雀状态切换 | `pending` |
| T-20260428-208 | [domains/gov_policy] harness_rules 实装 | 把 T-20260427-113 的占位 stub 实装：`compliance_blocklist`（结合爬虫硬规则禁词）、`field_hit_thresholds`（关键 6 字段命中率）、`schema_path` 指向 v1.json | 注入到 `infra/harness`，跑国务院 + 1 个部委用例验收 | `pending` |
| T-20260428-209 | [docs/prod-spec] codegen-platform-v1 规格 | 把本研究提案落地为正式 spec `docs/prod-spec/codegen-platform.md`：Task 模型字段定义（与外部项目对齐）、状态机、harness 接口、TaskSource 接口 | 与外部 task 项目负责人对齐确认；评审通过 | `pending` |
| T-20260428-210 | [端到端验收] 复刻已存在部委任务 | 选一个已合并的部委适配器（如 `ndrc`），构造一个 `task_type=create` 的 task，让 codegen worker 自动重新产出 `ndrc.py` 到隔离分支；harness 全绿 + PR 创建 | 工件：自动生成的 PR URL + harness 报告；与原手写版 diff < 30% 行差异 | `pending` |
| T-20260428-212 | [infra/codegen + sandbox] Tier 划分与分级合并门槛 | 实现 `auto-merge-policy.md` §2：按 PR diff 路径计算 tier；sandbox 写白名单按 tier 注入；tier-3 路径出现 → 直接拒绝 | 单元测试：构造 3 类 PR diff，tier 判定与白名单生效正确；tier-3 越权被拦截 | `pending` |
| T-20260428-213 | [infra/harness] 加压门槛与扩展禁词 | 落实 §3：golden ≥ 10 / E2E ≥ 20 行 / schema ≥ 98% / 关键字段 ≥ 99% / 30+ 条扩展禁词 (`infra/harness/blocklist.yaml`)；tier-2 现役回归 | 单元测试：注入合规失败 / 字段缺失 / 现役回归失败用例，harness 全部拦截 | `pending` |
| T-20260428-214 | [infra/scheduler] 渐进 canary + 自动回滚 | 实现 §4：4 档分流 (0/1/10/100%)；按 tier 不同观察期；任一失败阈值命中 → 回退 adapter + 创建 fix-task；与 §6 warm-up 联动 | 单元测试：模拟阶段升降级；模拟失败触发回滚与 fix-task 写库 | `pending` |
| T-20260428-215 | [scripts] 自动合并 IM 审计与回放链路 | 实现 §5：4 类事件 webhook 投递；`crawl_task.audit_log` JSON 字段沉淀 PR/harness/agent/canary/rollback 链路 | 单元测试：4 类事件均有 webhook 与 audit_log；缺一项即拒绝进入 tier-1 | `pending` |
| T-20260428-216 | [infra/http] 限流分级启动（warm-up） | 实现 `infra-fetch-policy.md` §2.3：4 级阶梯 + 升降级触发；与 canary 阶段联动；默认参数从 env 读取 | 单元测试：mock 4xx 比例触发降级；mock 反爬命中触发 L0+cooldown；正常路径升级到 L3 | `pending` |

## 4. 边界护栏

- **不建** `infra/task_api/` 与 `infra/task_store/`：Task 提交与持久化属于外部独立项目。
- **不预先选定**外部 task 项目的接口形态：T-205 提供协议抽象 + Mock，等外部项目接口稳定后再实装 `HttpTaskSource` 具体类。
- **不在本期** decide 金丝雀阈值（开放问题 6）；先以环境变量暴露，待运行一段时间后定。
- **不引入**邮件、OTel（继续遵守 TD-002、TD-005）。
- **不让** codegen 在生产数据库上跑：只允许 sandbox + dev profile。
- **不允许** agent 写沙箱白名单外路径（包括 `infra/`、`docs/architecture.md` 等）。
- **不做** 站点版本巡检（`infra/version_guard/`）。已设计于 `infra-resilience.md` §3，登记 TD-012 暂缓。

## 5. 完成标准

`green` 仅当：

- 第 3 节 10 个任务全部 `completed`
- T-210 端到端验收 PR 真实生成且 harness 全绿
- `docs/prod-spec/codegen-platform.md` 由外部 task 项目负责人确认对齐
- 本文件移到 `docs/exec-plan/archive/YYYY-Www/`
