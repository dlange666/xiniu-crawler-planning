# plan-20260428-webui-bootstrap

## 1. 元信息

- **Plan ID**：`plan-20260428-webui-bootstrap`
- **关联规格**：`docs/prod-spec/webui.md`
- **状态**：`active`
- **负责角色**：`Planner`

## 2. 目标

实现 WebUI MVP：FastAPI 提供 `/api/*` JSON，React + Ant Design Pro 前端展示
任务、监控和采集结果数据；MVP 使用 `DevBackend` 鉴权，所有写操作写入
`webui_audit`。rev 6 起 Jinja 页面只作为遗留 fallback，不再作为主要 UI。

## 3. 原子任务列表

| 任务 ID | 标题 | spec_ref | 实现细节 | 验证方式（Evaluator） | 状态 |
|---|---|---|---|---|---|
| T-20260428-301 | [webui] FastAPI UI/API MVP 联通 | `webui.md` rev 5；`data-model.md` §4.1, §4.7 | 新增顶层 `webui/`；FastAPI + Jinja2 MVP 页面；`/api/tasks` 与 `/api/tasks/{id}/timeseries`；DevBackend；SQLite MVP 表；写审计 | pytest 覆盖页面 200、API JSON、POST 新任务写 `crawl_task` + `webui_audit`、viewer 写操作 403、production+dev 拒绝启动 | `verifying` |
| T-20260428-302 | [webui/frontend] React + Ant Design Pro 重写 | `webui.md` rev 12 §2, §3, §7, §12 | 新增 `webui/frontend`：React + TypeScript + Vite + Ant Design ProComponents；FastAPI 新增 `/api/tasks/{id}`、`/api/adapters`、`/api/tasks/{id}/items/{raw_id}` 并托管 `/ui` SPA；前端实现任务列表、source 详情单表 Tabs（全部 / 已采集 / 未采集）、列表只显示按钮/状态、站内采集详情页、详情页 Attachments 下展开 depth+1 子链接、adapter 列表 | `npm run build` 成功；pytest 覆盖新增 API；本地 `/ui` 可访问并展示 runtime DB 数据 | `in_progress` |

## 4. 边界护栏

- 不接 OAuth/OIDC；继续登记在 TD-018。
- 引入 React/Node 构建链仅限 `webui/frontend/`；生产仍由 FastAPI 托管构建产物，不运行 Node 服务。
- 不使用 CDN 作为运行时依赖。
- 不实现 admin 限速、disable adapter 的真实写入路径；首版保留权限矩阵与禁用入口。
- 不实现 `metric_snapshot` / `alert_history` 体系；监控页先从既有采集表降级聚合。

## 5. 完成标准

`green` 仅当：

- T-20260428-301 在对应任务文件中标记 `completed`
- pytest 中 WebUI 相关用例通过
- `docs/eval-test/` 写入 WebUI MVP 验收证据
- 本地 `uv run python scripts/run_webui.py` 可启动页面
