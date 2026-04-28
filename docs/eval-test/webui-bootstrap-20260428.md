# WebUI MVP 验收报告

> **类型**：`acceptance-report`
> **关联**：`plan-20260428-webui-bootstrap` / `T-20260428-301`
> **验证 spec**：`validates: webui.md §2, §3, §4, §5, §6, §7, §12; data-model.md §4.1, §4.7`
> **作者**：Evaluator
> **日期**：2026-04-28
> **判定**：`green`

## 1. 背景与目的

验证 WebUI MVP 是否提供可见浏览器页面，并完成 FastAPI 页面、`/api/*`、
SQLite 任务表和 `webui_audit` 的联通。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 无 WebUI 实现，仅有 spec |
| Candidate（候选） | `webui/` FastAPI + Jinja2 页面 + 本地 JS/CSS + SQLite MVP schema |
| 数据切片 | pytest 临时 SQLite DB；含 1 个 `crawl_task`、1 条 `fetch_record`、1 条 `crawl_raw` |
| 评估口径 | 页面 200、API JSON、页面展示 API 数据入口、写操作审计、权限、生产 dev auth 拒绝 |
| 复现命令 | `uv run pytest tests/webui tests/infra/test_storage.py -q`; `uv run pytest -q`; `uv run ruff check webui tests/webui infra/storage/sqlite_store.py scripts/run_webui.py` |
| 临时 DB 路径 | pytest `tmp_path` 自动创建并清理 |

## 3. 度量结果 · 聚合

| 指标 | Control | Candidate | Δ | 备注 |
|---|---|---|---|---|
| WebUI 目标测试 | 0 | 18 passed | +18 | 覆盖页面/API/schema |
| 全量测试 | 0 | 80 passed | +80 | 仓库现有测试无回归 |
| ruff | 未覆盖 | passed | +1 | WebUI 与触达文件 lint 通过 |

## 4. 度量结果 · 按切片

| 切片 | 结果 | 证据 |
|---|---|---|
| 页面渲染 | green | `/`、`/tasks`、`/tasks/{id}`、`/tasks/{id}/items`、`/monitor` 返回 HTML 200 |
| API 联通 | green | `/api/tasks` 返回任务列表；`/api/tasks/{id}/timeseries` 返回 series |
| Source drill-down | green | `/tasks/{id}` 展示 URL 明细；`/api/tasks/{id}/urls` 返回 depth 分布、URL 状态和 raw 摘要 |
| 已抓取/跳转链接分离 | green | `/api/tasks/{id}/urls?kind=fetched` 只返回 fetch/raw 结果；`/api/tasks/{id}/urls?kind=jump&depth=2` 只返回待抓跳转链接；React 详情页拆成两张独立分页表 |
| URL 分页与紧凑 UI | green | `/api/tasks/{id}/urls` 返回 `total/limit/offset`；详情页显示当前范围与上一页/下一页 |
| React / Ant Design Pro 重写 | green | `webui/frontend` 使用 React + TypeScript + Vite + Ant Design ProComponents；`npm run build` 成功；FastAPI `/ui` 可托管构建产物 |
| 写审计 | green | `POST /tasks` 后 `crawl_task.created_by=alice@local`，`webui_audit.action=submit_task` |
| 权限 | green | `role=viewer` 写 `/tasks` 返回 403 |
| 生产保护 | green | `WEBUI_ENV=production` + `WEBUI_AUTH_MODE=dev` 创建 app 抛错 |

## 5. 异常案例

无阻塞异常。OAuth/OIDC、admin 限速和 `metric_snapshot` 仍按 spec 暂缓，不纳入本次验收。

## 6. 结论与决策

- **判定**：`green`
- **理由**：页面、API、权限、审计与生产保护均有自动化测试覆盖；全量测试无回归。
- **风险**：前端图表为本地轻量 JS 渲染；后续若引入 vendored Chart.js/HTMX，需要补静态资源许可证与浏览器回归。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| OAuth/OIDC | TD-018 |
| 指标/告警体系 | TD-013 / `infra-observability.md` |
| admin 限速真实写操作 | 后续 WebUI admin task |
| 关闭哪些 task / plan | PR 创建后关闭 `T-20260428-301`；计划保留到 PR green |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-28 | 初版 |
| rev 2 | 2026-04-28 | 补充 source drill-down 验收：URL 数量、depth 分布、URL 明细和 raw 摘要 |
| rev 3 | 2026-04-28 | 补充紧凑 Ant Design 风格与 URL 服务端分页验收 |
| rev 4 | 2026-04-28 | 补充 React + Ant Design ProComponents 重写验收 |
| rev 5 | 2026-04-28 | 补充已抓取链接与跳转/发现链接分离、depth 过滤验收 |
