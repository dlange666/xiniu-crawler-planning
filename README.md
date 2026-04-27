# xiniu-crawler

烯牛政策图谱项目的 AI-First 通用爬虫平台。第一阶段目标：把全国产业政策
（中央 + 国务院 + 国务院部委 + 31 省市自治区政府门户）按"采集入库 → 内容
保真留存 → AI 结构化 36 字段 JSON"的链路打通。

仓库采用 `docs-first control plane + bounded contexts` 模式：规格、计划、
实验、评估和代码实现都在同一仓库内维护，`docs/` 负责控制面，
`domains/` 负责业务实现，`infra/` 负责共享技术能力。

## Start Here

- `AGENTS.md` —— 仓库地图、工作流、硬规则
- `CLAUDE.md` —— 会话级强约束
- `docs/architecture.md` —— 控制面/数据面分层与依赖规则
- `docs/product-sense.md` —— 产品目标、使用场景、核心指标
- `docs/prod-spec/policy-graph-v1.md` —— 政策图谱 v1 产品规格
- `docs/research/` —— 研究底稿（AI-First 爬虫总体架构、政策图谱策划、第一阶段数据源）

## Repository Layout

- `docs/` 控制面文档，按 `workflow / artifact / long-lived` 管理
- `domains/<context>/` 按 bounded context 组织的业务代码与测试
- `infra/` 跨 context 复用的技术能力，不承载业务规则
- `scripts/` 仓库级 CLI 入口
- `runtime/` 本地运行时数据、临时实验产物、SQLite 数据库
- `skills/` crawler-workflow 系列 skill 源

## Tech Stack

- Python + `uv`
- 元数据：PolarDB（生产）/ SQLite（开发测试）
- 原始页与附件：阿里云 OSS（生产）/ 本地文件系统（开发测试）
- 采集策略：static-first → 接口拦截 → SSR/DOM → headless 渲染（按需）
- 解析层去重：`content_sha256` 严格去重；simhash 仅做相似聚类信号

## Working Rules

- 修改仓库文件前，先读 `AGENTS.md`
- 代码变更默认遵循 `branch -> PR`
- 评估与实验结论进入 `docs/eval-test/`，不要把运行输出写进 `docs/`
- 不绕过验证码/登录/付费墙/robots 明示拒绝
- 不要把每个 `docs/` 子目录都机械地改造成 `active/completed/archive`

## Current Focus

- M0 项目骨架（控制面 + workflow）
- M1 单源跑通：国务院文件库静态抓取 + 原始页落盘
- M2 多源 + 解析层去重：8 个国务院部委
- M3 AI 结构化：36 字段 prompt → JSON 写库
