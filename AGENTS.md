# xiniu-crawler — Agent Map

Read this file before starting work. It is the repository control map.

本文件只描述四件事：**仓库地图（Repository Map）**、**角色（Roles）**、
**工作流（Operating Flows）**、**硬规则（Hard Rules）**。任何业务/产品
相关的表述（采集对象、字段定义、产品形态）都不写在此处，统一沉淀在
`docs/prod-spec/<domain>.md` 与对应 `domains/<context>/` 下。

## Repository Map

| Path | Purpose |
|---|---|
| `CLAUDE.md`, `AGENTS.md`, `README.md` | 根控制文档与人类入口 |
| `docs/architecture.md`, `docs/product-sense.md` | 架构、产品方向（不含具体业务字段） |
| `docs/domains-overview.md`, `docs/gov-policy-layout.md`, `docs/infra-overview.md` | 业务域与基础设施目录"门牌"，归档自原 `*/README.md` |
| `docs/exec-plan/`, `docs/task/`, `docs/experiment/`, `docs/cleanup-log.md` | 工作流文档：交付计划、任务状态、实验执行、清理记录 |
| `docs/eval-test/` | 评估证据与回放产物 |
| `docs/prod-spec/`, `docs/research/` | 长期参考文档：产品规格与研究底稿（业务细节归此） |
| `domains/<context>/` | bounded-context 业务代码 |
| `infra/` | 跨上下文复用的技术能力，不承载业务规则 |
| `scripts/` | 仓库级 CLI 入口 |
| `runtime/` | 本地运行时数据、临时 DB、抓取缓存 |
| `skills/` | crawler-workflow 系列 skill 源 |

## Roles

| Role | Responsibility |
|---|---|
| `Planner` | 锁定上下文与作用域，更新规格/架构，输出已批准的执行计划 |
| `Generator` | 实现单个原子任务，更新触达的文档/测试，更新 `docs/task/` 下对应任务文件 |
| `Evaluator` | 独立验证、记录 `green`/`red` 证据、关闭任务/计划状态 |
| `Cleaner` | 例行整洁、归档噪声、记录清理、把非紧急债务推后 |

## Operating Flows

每个任务都用 `/crawler-workflow` 起步。

### Main Delivery Loop
`Spec -> Plan -> Task -> Code -> Evidence`
`Planner` 更新 spec 并写计划。`Generator` 实现一个已批准任务并更新
`docs/task/active/` 下的任务文件。`Evaluator` 把证据写入 `docs/eval-test/`
并更新同一任务状态。`Red` 退回 `Generator`；只有计划全部完成时才 `green`。

### Experiment Flow
`Hypothesis -> Setup -> Execution -> Artifact -> Communication -> Closure`
`Generator` 在隔离 worktree 上运行 additive 候选，`Evaluator` 在
`docs/eval-test/` 写下 retained-vs-candidate 工件。被拒绝的 `Red` 候选代码
不得进入 merged `main`。

### Cleanup Flow
扫描过期代码与运行时产物，清理未引用快照，合并幸存路径，同步文档，并把
记录写入 `docs/cleanup-log.md`。

### Tech Debt Flow
非紧急债务记录在 `docs/exec-plan/tech-debt-tracker.md`。只有 `Planner` 显
式提升后才进入活跃工作。

## Hard Rules

### Delivery Controls
- `Generator` 一次只做一个已批准的原子任务。
- 任务 ID 按日期编号。`101+` 用于活跃任务，`201+` 用于新计划切片；同一日期同一分支/PR 线保持在同一百位段；并行线另开新百位段。
- 如果某文件改动型任务处于 `in_progress`，必须先创建并切换到对应分支再编辑文件。
- 并行非 `main` 会话使用专用 worktree：`git worktree add /Users/wangjisong/xiniu/code/xiniu-crawler-<topic> <branch>`，合并后 `git fetch --prune && git worktree prune` 或 `git worktree remove <path>`。
- 默认粒度：`one branch -> one active task -> one draft PR`。多任务共享分支仅当属于同一已批准切片。
- 同任务线后续工作留在当前分支/PR；真正不同的范围才另开分支。
- 分支命名：`agent/<type>-YYYYMMDD-<topic>`（type ∈ `feature|cleanup|fix|docs|infra|spike`）。PR 标题：`<type>(<scope>): <summary>`。
- 任务发现直接扫描 `docs/task/active/`、`docs/task/completed/`、`docs/task/archive/`，不另设顶层任务索引文件。

### Crawler-Specific Hard Rules
- **不绕过保护措施**：禁止绕过验证码、登录认证、付费墙、技术 challenge、robots 明示拒绝；不得使用专门用于绕过保护的工具/库。识别 → 降速/暂停/人工审核，是允许的全部动作。
- **robots 遵从**：以 RFC 9309 为基线。robots 5xx 视为 complete disallow；24h 内刷新缓存；不依赖 vendor 行为差异。
- **礼貌性与限速**：以 host 为最小礼貌性单元，遵守 `Retry-After`，对 429/503 走"Retry-After 优先 + 指数退避 + 抖动 + cooldown"。
- **原始页留存**：所有抓取结果的原始字节与 HTTP 元数据必须可回放；解析层与原始层分离。
- **去重位置**：不在 source（采集）层去重；在解析/入库层做内容指纹严格去重，simhash 仅作信号，**不自动合并**。
- **PII 与合规**：默认不抽身份证号、手机号、邮箱等敏感字段；任务创建必须填写用途、责任人、范围；删除/TTL 链路从设计起预留。
- **AI 用法**：AI 只放在 URL 排序、页面分类、反爬识别、内容抽取等高不确定决策点；规则优先，AI 兜底；LLM 不进入所有请求主路径。
- **抓取层级顺序**：`feed/sitemap → static HTML → 接口拦截（GraphQL / JSON API）→ SSR/DOM → headless 渲染`。仅在命中信号时进入下一档。

### Architecture, Naming, and Reuse
- 上下文归属先于实现。架构边界变更时，先更新 `docs/architecture.md` 再写代码。
- 业务代码留在正确 bounded context（`domains/<context>/`）；`infra/` 只放共享技术能力。
- 命名要承载具体职责。避免 `common.py`、`utils.py`、`helper.py` 等空名。
- `scripts/` 不得相互 import；可复用的原语沉到 `infra/<surface>/` 或正确的 domain 模块。

### Data Model Authoritative Source
- 所有表 DDL 的**唯一权威源**是 `docs/prod-spec/data-model.md`。
- 其它 spec（如 `codegen-output-contract.md` / `infra-deployment.md`）描述设计动机与字段语义，**不再维护表 DDL**；如需 SQL 定义，引用 data-model.md 对应小节。
- 新增表必须先在 owning spec 写设计动机，再到 data-model.md 落 DDL；两个 spec 的修订历史互相引用。
- 尽量不使用 JSON 字段。仅在动态结构 / 一次性写入 / 不参与 SQL 检索三类场景才允许（详见 data-model.md §1.3）。

### Spec Versioning
- spec 文件名**不带版本号**（用 `infra-fetch-policy.md` 而非 `infra-fetch-policy-v1.md`）。
- 每份 spec 顶部有引用块 frontmatter：`> **版本**：rev N · **最近修订**：YYYY-MM-DD · **状态**：active|draft|deprecated`。
- 每份 spec 底部有 `## 修订历史` 表（rev / 日期 / 摘要 / 关联 PR）。
- 任何 spec 的**实质性改动**（影响实现 / 契约 / 默认值 / 接口）必须同 PR 内：(a) 追加 `## 修订历史` 一行；(b) bump 顶部 rev 号与 `最近修订` 日期。breaking change 在摘要前加 **[breaking]** 前缀。
- 纯排版、链接修复、错别字不算实质性改动，可不更修订历史。
- 模板：`docs/prod-spec/template.md`。其它 docs 子目录模板：`docs/{exec-plan,task,experiment,eval-test}/template.md`。

### Docs, Data, and Runtime
- `docs/` 只放文档。新 Markdown 文件用 kebab-case 命名。
- `docs/` 按生命周期分类，不强行套统一目录形态：
  - workflow: `docs/exec-plan/`、`docs/task/`、`docs/experiment/`、`docs/cleanup-log.md`
  - artifact: `docs/eval-test/`
  - long-lived: `docs/prod-spec/`、`docs/research/`、`docs/architecture.md`、`docs/product-sense.md`
- `docs/task/` 是状态索引化的工作流目录：active/completed/archive 直接扫描。
- `docs/exec-plan/active/` 是新活跃计划目录；关闭后归档到 `docs/exec-plan/archive/YYYY-Www/`。
- 运行时数据存放规则：
  - **开发/测试**：SQLite 落在 `runtime/db/`；本地原始页缓存落在 `runtime/raw/`（gitignore）。
  - **生产**：元数据库使用外部 **PolarDB**；原始页与附件使用 **阿里云 OSS**；SQLite 仅用于本地复现。
- 运行时产物不入 git。`runtime/db/test_*.db` 是临时的：任务/实验关闭后清理，最多保留最近 5 份。
- 大作业本地脚本运行；agent 会话只做有限验证。文件 `>=10 MB` 需批准，`>=50 MB` 不允许，`>=100 MB` 禁止。
- 邮件通知本期不接入；保留 hook 位置，待后续按需补齐。

## Skills
- 在每个任务开始时调用 `/crawler-workflow`。当工作流治理变更时，更新 `skills/` 下源文件并重装受影响的 skill 后再关闭任务。
