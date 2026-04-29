# plan-20260429-render-codegen-platform

## 1. 元信息

- **Plan ID**：`plan-20260429-render-codegen-platform`
- **关联规格**：`docs/prod-spec/infra-render-pool.md`；`docs/prod-spec/codegen-output-contract.md`；`docs/prod-spec/codegen-auto-merge.md`
- **状态**：`completed`
- **负责角色**：`Planner / Generator / Evaluator`

## 2. 目标

交付 headless render pool 与 codegen 平台 infra 化的第一批可合入基础能力：
render 先实现判定、预算配置、同步池化接口和 fake/backend 可测试入口；codegen
先实现 agent backend、sandbox 写入白名单、harness 结果模型、TaskSource 与
worker 主循环骨架。Playwright 真浏览器、自动 PR、canary/rollback 和生产调度
仍留给后续原子任务。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-1201 | [infra/render] render decision 与 pool 基础能力 | `infra-render-pool.md` §3-§5, §7；`infra-crawl-engine.md` §10 | 新建 `infra/render/`：类型、配置、判定、同步 `RendererPool`、可注入 backend；默认 disabled；challenge/login/paywall/robots/anti-bot 一律 blocked；CrawlEngine 接受 renderer 注入并在 adapter 明确 `should_render` 时使用 rendered HTML | `uv run pytest tests/infra/test_render_pool.py tests/infra/test_crawl_render.py -q`；`uv run ruff check infra/render infra/crawl/runner.py tests/infra/test_render_pool.py tests/infra/test_crawl_render.py` | `completed` |
| T-20260429-1202 | [infra/codegen] agent/sandbox/harness/worker 基础骨架 | `codegen-output-contract.md` §3, §5-§6；`codegen-auto-merge.md` §2-§3 | 新建 `infra/agent/`、`infra/sandbox/`、`infra/harness/`、`infra/codegen/`：agent backend 协议和 OpenCode/Mock 实现，路径白名单校验，harness gate/result 模型和命令 runner，TaskSource 协议与 worker run-once 主循环 | `uv run pytest tests/infra/test_agent_backend.py tests/infra/test_sandbox.py tests/infra/test_harness.py tests/infra/test_codegen_worker.py -q`；`uv run ruff check infra/agent infra/sandbox infra/harness infra/codegen tests/infra/test_agent_backend.py tests/infra/test_sandbox.py tests/infra/test_harness.py tests/infra/test_codegen_worker.py` | `completed` |
| T-20260429-1203 | [docs/eval] 记录 render + codegen infra 基础切片验收证据 | `infra-render-pool.md` §11；`codegen-output-contract.md` §5；`codegen-auto-merge.md` §8 | 更新关联 spec/architecture/plan/task，写 `docs/eval-test/render-codegen-platform-20260429.md` | targeted pytest/ruff、full pytest、full ruff、JSON 校验、diff check | `completed` |

## 4. 边界护栏

- 不实现 Playwright 真浏览器下载与运行；`playwright_backend` 只提供可选 backend 包装，未安装依赖时显式报错。
- 不做验证码、登录、付费墙、challenge、stealth、指纹伪装或代理轮换。
- 不让 render 成为默认路径；必须由 adapter `render_mode=headless` 或 `should_render` 信号触发，且 `RENDER_POOL_ENABLED=true` 才执行。
- 不实现自动 PR 创建、自动合并、canary 升档、自动回滚；本切片只交付 infra 抽象和本地可测试主循环。
- 不接外部 Task API 的真实 HTTP 协议；TaskSource 先提供协议与内存实现。

## 5. 完成标准

`green` 仅当：

- T-20260429-1201、T-20260429-1202、T-20260429-1203 均有任务状态记录。
- `infra/render/`、`infra/agent/`、`infra/sandbox/`、`infra/harness/`、`infra/codegen/` 有单元测试覆盖。
- 默认配置下 headless 不会静默执行；受保护/反爬信号均被判定 blocked。
- codegen worker 能用 fake TaskSource + MockAgent + fake harness 跑通成功和失败分支。
- 针对性与全量测试、ruff、diff check 通过。
