# plan-20260429-probe-capability

## 1. 元信息

- **Plan ID**：`plan-20260429-probe-capability`
- **关联规格**：`docs/prod-spec/infra-crawl-engine.md` §6.3；`docs/prod-spec/codegen-output-contract.md` §3.1；`docs/prod-spec/infra-render-pool.md` §1
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

为 codegen agent 提供受控的站点探查 infra：在生成 adapter 前，先由仓库脚本
判断入口 URL 更适合走 static HTML、JSON API，还是需要未来 render-pool 支持，
并把原始响应与判定结果留存在 `runtime/probe/<host_slug>/` 供回放与审计。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260429-401 | [infra/source-probe] 提供受控 fetch/json/render-required 探查能力 | `infra-crawl-engine.md` §6.3；`codegen-output-contract.md` §3.1；`infra-render-pool.md` §1 | 新增 `infra/source_probe` 与 `scripts/probe_source.py`；支持 robots gate、静态 HTML、JSON 响应、HTML 内 JSON 候选、JS redirect、SPA shell 判定；输出 `probe-result.json` 与可回放 artifact | 单测覆盖 JSON 候选、JS redirect、SPA shell、robots disallow；ruff、py_compile、全量 pytest；用 `www.gov.cn` 与 `flk.npc.gov.cn` 做 live probe 证据 | `verifying` |

## 4. 边界护栏

- 本计划不实现 Playwright/Selenium/headless 浏览器池；`headless_required` 只作为能力缺口判定。
- 本计划不绕过验证码、登录认证、付费墙、技术 challenge 或 robots 明示拒绝。
- 本计划不修改 adapter hook 运行期约束；hook 内仍不得自行发网络请求。
- 本计划不把探查 artifact 放入 git；`runtime/probe/` 仅作本地运行时证据。
- 本计划不改变 source 层去重位置；探查只做入口能力判定与原始响应留存。

## 5. 完成标准

`green` 仅当：

- T-20260429-401 在任务文件中标记 `completed`
- `docs/prod-spec/` 中受影响规格已 bump rev 与修订历史
- `uv run pytest tests/infra/test_source_probe.py -q` 通过
- `uv run ruff check infra/source_probe scripts/probe_source.py tests/infra/test_source_probe.py` 通过
- `uv run pytest tests/ -q` 通过
- `docs/eval-test/probe-capability-20260429.md` 记录验收证据
