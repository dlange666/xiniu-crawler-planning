# Webui · 任务后台 + 采集监控 + 结果浏览（自建轻量看板）
> **版本**：rev 7 · **最近修订**：2026-04-28 · **状态**：active
>
> **实施状态**：MVP 实施（替代原 TD-014）。OAuth 接入暂缓（TD-018）；MVP 用
> `DevBackend` 免登模式跑通。

> **背景**：暂无 Grafana / 其他 BI / 任务管理后台。需要让 ops/dev/业务运营在
> 浏览器内完成三件事：
>
> 1. 提交 / 改 / 取消采集任务（写）
> 2. 看在跑任务进度、host 健康、失败堆栈（监控）
> 3. 翻 `crawl_raw` 看采集结果、原始 HTML（浏览）
>
> 三件事共用一个 FastAPI API 服务和一个 React 前端。本 spec 给出**FastAPI
> `/api/*` + React / Ant Design Pro 前端 + 外部 OAuth**（MVP 用 DevBackend
> 占位）的最小方案。

## 1. 范围

### 1.1 三类 UI 面（按路由分组合并）

| 面 | 路径前缀 | 主要用户 | 写？ | 数据来源 |
|---|---|---|---|---|
| **A. 任务后台** | `/tasks*`、`/admin/*` | 业务运营 / dev | ✓ | `crawl_task` |
| **B. 采集监控** | `/`、`/monitor*`、`/hosts*`、`/adapters*`、`/api/*` | ops / dev | ✗ | `crawl_task_execution` + `url_record` + `fetch_record` + `metric_snapshot`(暂缓) |
| **C. 结果浏览** | `/tasks/{id}/items*`、`/browse*` | dev / 数据消费方 | ✗ | `crawl_raw` + Blob |

### 1.2 关注点

| 关注点 | 关键问题 | 来源 |
|---|---|---|
| 任务总览 | 哪些任务在跑？进度多少？ | `crawl_task` + `crawl_task_execution` + `url_record` |
| 任务提交 | 新建任务、调参数、取消、复制启动命令 | `crawl_task` 写 |
| 抓取健康 | frontier 积压？host 状态？反爬事件？ | `url_record.frontier_state` + `fetch_record.error_kind` + `metric_snapshot`(暂缓) |
| 解析与抽取 | 解析失败率？AI 调用？schema 合格率？ | `metric_snapshot` AI 组（TD-013） |
| 结果浏览 | 翻 crawl_raw、看原始 HTML、按域过滤 | `crawl_raw` + `BlobStore.get` |
| 存储与成本 | OSS 增长？AI 费用？预算剩余？ | `metric_snapshot` OSS/AI 组（TD-013） |
| 告警历史 | 最近触发了什么？ | `alert_history`（TD-013） |
| Adapter 健康 | 哪些站点适配器在跑？degraded？ | `infra.adapter_registry` 列表 + `fetch_record` 错误率 |

## 2. 技术栈

```
浏览器 ─→ React SPA（Ant Design Pro / ProComponents）
            └─ /api/* JSON ─→ FastAPI（同 crawler 进程或独立进程，二选一）
                              └─→ 读 PolarDB / SQLite（业务表 + 观测表）
```

| 组件 | 选型 | 理由 |
|---|---|---|
| API 框架 | FastAPI | 保持 crawler 后端依赖与鉴权/审计入口 |
| 前端框架 | React + TypeScript + Vite | 明确进入真实前端工程，不再用 Jinja 仿制复杂后台 |
| UI 框架 | Ant Design + Ant Design ProComponents | 直接使用成熟后台组件（ProLayout / PageContainer / ProTable / StatisticCard） |
| 图表 | Ant Design 统计组件 + 后续可接 AntV | MVP 先展示任务、URL、状态；复杂图表后续接入 |
| 鉴权（MVP） | `DevBackend`（env 注入用户名 + role，免登） | 本地 / 内网受信环境足够 |
| 鉴权（生产） | OAuth 2.0 + OIDC（Authorization Code + PKCE）+ 签名 cookie | 不在本仓库存凭据；TD-018 |
| 静态资源 | FastAPI 托管 `webui/frontend/dist` | standalone 部署时一个进程即可打开 WebUI |
| Session | `starlette.SessionMiddleware`（签名 cookie，无服务端 session 存储） | 多副本无状态 |

**没有**：Vue、Webpack、单独的 Node 生产服务、Grafana、Tableau、本地密码库、Redis session、CDN 运行时依赖。

## 3. 目录与代码落点

```
webui/                         ← 顶层（与 infra/ domains/ docs/ 平级）
├── app.py                     FastAPI 应用工厂；中间件；路由挂载
├── config.py                  env 配置（AUTH_MODE / SESSION_SECRET / ...）
├── auth/
│   ├── backend.py             AuthBackend Protocol
│   ├── dev.py                 DevBackend（MVP 用）
│   ├── oauth.py               OAuthBackend（TD-018，先留空文件）
│   ├── mock.py                测试用
│   ├── session.py             签名 cookie helper
│   ├── roles.py               claims → role 映射
│   └── deps.py                current_user / require_role FastAPI dependency
├── routes/
│   ├── tasks.py               /api/tasks*
│   ├── monitor.py             /api/health、/api/version、/api/adapters
│   ├── browse.py              /api/tasks/{id}/items*
│   └── admin.py               [A] /admin/*
├── stores/                    数据访问层（只读 SQL，与 infra.storage 分离）
│   ├── task_store.py          crawl_task CRUD
│   ├── progress_store.py      url_record / fetch_record 聚合
│   └── audit_store.py         webui_audit 写入
├── frontend/
│   ├── package.json           React / Ant Design Pro 依赖
│   ├── vite.config.ts         dev server 代理 /api 到 FastAPI
│   └── src/                   页面、API client、主题
└── templates/、static/         rev 5 Jinja 版本遗留；React 版稳定后清理
scripts/
└── run_webui.py               独立入口（uvicorn webui.app:app）
```

`scripts/view_crawl.py`（CLI 兜底）保留，与 webui 的 `/browse` 共存。

## 4. 路由与权限矩阵

### 4.1 三档角色

```
viewer    →  全部读路径
operator  →  viewer + 写：POST /tasks、cancel、pause
admin     →  operator + 危险操作：disable adapter、改限速、admin 页
```

### 4.2 矩阵

| 路径 | 方法 | 最低角色 | UI 面 | 备注 |
|---|---|---|---|---|
| `GET /` | GET | viewer | B | 仪表盘首页 |
| `GET /tasks` | GET | viewer | A+B | 任务列表 + 筛选 |
| `GET /tasks/{id}` | GET | viewer | A+B | 任务详情：参数 + 漏斗 + 时序 |
| `GET /tasks/{id}/items[/{n}]` | GET | viewer | C | crawl_raw 翻页 + 单条详情 |
| `GET /tasks/new` | GET | **operator** | A | 提交表单 |
| `POST /tasks` | POST | **operator** | A | 提交任务 |
| `POST /api/tasks/{id}/cancel` | POST | **operator** | A | 软取消 |
| `POST /api/tasks/{id}/pause` | POST | **operator** | A | 暂停（依赖 TD-010） |
| `GET /monitor` | GET | viewer | B | 全局监控 |
| `GET /hosts[/{host}]` | GET | viewer | B | 依赖 metric_snapshot（TD-013） |
| `GET /adapters` | GET | viewer | B | 列出 `infra.adapter_registry.list_all()` |
| `GET /api/tasks/{id}/timeseries` | GET | viewer | B | Chart.js 取数 |
| `POST /admin/adapters/{host}/disable` | POST | **admin** | A | 二次确认 |
| `POST /admin/host/{host}/rps` | POST | **admin** | A | 改限速 |
| `GET /api/health`、`GET /api/version` | GET | 匿名 | — | 探针 |
| `GET /login`、`GET /auth/callback`、`GET /logout` | GET | 匿名 | — | OAuth 流程（TD-018） |

**默认拒绝**：路由未在矩阵中声明 → CI 检查 + 启动期 lint 拒绝。

## 5. 鉴权设计

### 5.1 AuthBackend 抽象

```python
class AuthBackend(Protocol):
    def login_url(self, *, redirect_to: str) -> str: ...
    def handle_callback(self, request) -> User: ...
    def logout_url(self, *, post_logout: str) -> str: ...

@dataclass
class User:
    sub: str            # IdP 主键（OAuth）或 dev id
    email: str          # 审计字段；OAuth 来自 claims，dev 来自 env
    role: str           # viewer / operator / admin
```

### 5.2 三种实现

| 实现 | 用途 | 启用条件 |
|---|---|---|
| `DevBackend` | 本地 / 内网受信 / MVP 默认 | `WEBUI_AUTH_MODE=dev` |
| `OAuthBackend` | 生产 | `WEBUI_AUTH_MODE=oauth`（TD-018） |
| `MockBackend` | 测试 | pytest fixture |

### 5.3 DevBackend 行为（MVP）

- 不跳转外部 IdP；启动时读 env：
  ```
  WEBUI_AUTH_MODE=dev
  WEBUI_DEV_USER=alice@local
  WEBUI_DEV_ROLE=operator
  ```
- 任何请求都被视为 `User(sub="dev", email=$WEBUI_DEV_USER, role=$WEBUI_DEV_ROLE)`
- **生产部署强制拒绝**：`WEBUI_ENV=production` 且 `AUTH_MODE=dev` → 启动失败
- 用途：本地开发、CI 测试、内网无 SSO 环境的 MVP 阶段

### 5.4 OAuthBackend 设计契约（TD-018 实现）

- 协议：OAuth 2.0 + OIDC，Authorization Code + PKCE
- 库：`authlib`
- 端点：`.well-known/openid-configuration` 自动发现
- 必备 env：
  ```
  WEBUI_AUTH_MODE=oauth
  WEBUI_OAUTH_ISSUER=https://idp.company.com
  WEBUI_OAUTH_CLIENT_ID=<client_id>
  WEBUI_OAUTH_CLIENT_SECRET=<client_secret>   # server-side 仅
  WEBUI_OAUTH_SCOPES=openid email profile groups
  WEBUI_SESSION_SECRET=<32+ 字节随机>
  ```
- token 验证：JWKS 验签，定期刷新公钥
- access_token 不存 cookie；userinfo 解出后丢弃
- 注销：仅清本地 cookie；SLO（同步注销 IdP session）暂不做

### 5.5 Role 映射

`webui/auth/roles.py`：

```toml
WEBUI_AUTH_ROLE_CLAIM = "groups"    # IdP claim 字段名

# 映射：从高到低匹配，命中即定级
WEBUI_AUTH_ROLE_MAP_ADMIN    = ["crawler-admins", "infra-admins"]
WEBUI_AUTH_ROLE_MAP_OPERATOR = ["crawler-operators", "data-team"]
WEBUI_AUTH_ROLE_MAP_VIEWER   = ["*authenticated*"]
```

未匹配但已认证 → 兜底 viewer（默认能看不能动）。

### 5.6 Session

- `starlette.SessionMiddleware`，签名密钥 `WEBUI_SESSION_SECRET`
- cookie：`webui_session`，`HttpOnly; Secure; SameSite=Lax; Max-Age=24h`
- 过期 → 重新走 `/login`
- 没有服务端 session 存储（无 Redis、无 session 表）

## 6. 审计

### 6.1 字段策略

| 表 | 字段 | 来源 |
|---|---|---|
| `crawl_task.created_by` | webui 写入时填 `User.email`（或 `sub`） | 已存在于 `data-model.md` §4.1.1 |
| `crawl_task_audit_event` | 已存在；webui 直接写 | `data-model.md` §4.1.7 |
| `webui_audit` | **新增**：所有 webui 写操作的细粒度日志（actor / action / target / payload / ip） | 本 spec 引入；DDL 见 `data-model.md` §4.7 |

### 6.2 中间件

`webui/app.py` 注册一个 `audit_middleware`：所有 `POST/PUT/DELETE/PATCH` 路由命中后写一行 `webui_audit`。GET 不写。

### 6.3 留存

`webui_audit` 至少留 180 天（与 TD-009 合规口径对齐）；超期归档到 OSS Parquet。

## 7. 页面与 API

### 7.1 页面

WebUI 必须先提供可操作的浏览器页面；API 是页面的数据源，不替代页面本身。
rev 6 起前端使用 React + Ant Design ProComponents，不再用 Jinja/CSS 仿制
复杂后台。视觉参考同类数据后台产品：深色/白色左侧导航、蓝色主操作、紧凑表格、
浅灰工作台背景、低留白密度、可快速扫描的指标卡与状态标签。

| 路径 | 内容 |
|---|---|
| `/ui`、`/ui/tasks` | React 任务列表：状态 / business_context 筛选；分页；显示 `created_by` |
| `/ui/tasks/{id}` | React source 详情：URL 数量、depth 分布、frontier 状态；分开展示已抓取链接（fetch/raw 结果）与跳转链接（已发现待抓 URL），均服务端分页 |
| `/ui/adapters` | React adapter 列表（`infra.adapter_registry.list_all()`），含 `last_verified_at` / `render_mode` |
| `/ui/monitor` | React 全局监控（跨任务，TD-013 前降级） |
| `/alerts` | 告警历史（TD-013） |
| `/spend` | LiteLLM 成本（TD-013） |
| `/admin/*` | 管理操作（admin 角色） |

### 7.2 API

API 由 FastAPI 提供，同一进程内服务页面与 JSON。页面内的表格/图表必须至少覆盖：

- `/tasks` 展示 `GET /api/tasks` 的任务列表数据
- `/tasks/{id}` 展示 `GET /api/tasks/{id}/timeseries` 的时序数据
- `/tasks/{id}` 分开展示 source 结果：已抓取链接表展示 fetch 状态与 `crawl_raw` 内容摘要；跳转链接表展示从页面发现但尚未 fetch 的 URL、depth、parent 与 discovery_source
- `/monitor` 展示跨任务聚合后的时序/状态数据
- `/tasks/{id}/items` 展示 `crawl_raw` 分页结果；大字段服务端分页，不一次性拉全量 JSON

| 端点 | 返回 | 鉴权 |
|---|---|---|
| `GET /api/tasks` | 任务列表（分页） | viewer |
| `GET /api/tasks/{id}` | 单任务详情 + progress | viewer |
| `GET /api/tasks/{id}/timeseries?metric=...&from=...&to=...` | 单任务指标时间序列 | viewer |
| `GET /api/tasks/{id}/urls?kind=all|fetched|jump&depth=&limit=50&offset=0` | 单 source URL 明细：total / limit / offset / depth_summary / items；`fetched` 返回已抓取链接与 fetch/raw 摘要，`jump` 返回已发现待抓跳转链接，`depth` 用于查看指定层级 | viewer |
| `GET /api/adapters` | adapter registry JSON | viewer |
| `GET /api/hosts/{host}/timeseries?metric=...` | 单 host 指标时间序列（TD-013） | viewer |
| `GET /api/spend?scope=...&from=...&to=...` | AI 成本聚合（TD-013） | viewer |
| `GET /api/alerts?from=...&limit=100` | 告警历史（TD-013） | viewer |
| `POST /api/tasks` | 提交任务 → 写 `crawl_task` | operator |
| `POST /api/tasks/{id}/cancel` | 软取消（runner 主循环检查 status） | operator |

返回格式统一：

```json
{ "labels": ["2026-04-28T08:00", ...], "series": [{ "name": "...", "values": [...] }] }
```

## 8. 部署形态

| 形态 | 说明 | 适用 |
|---|---|---|
| **嵌入 master 进程** | crawler master 进程同时跑 webui（同一 ASGI 应用） | 最省资源；MVP 形态 |
| **独立部署** | 单独跑 `scripts/run_webui.py`，只读 DB | 流量上来或需要独立扩缩 |

形态由 env `WEBUI_DEPLOY_MODE=embedded|standalone` 切换。MVP 用 standalone。

## 9. 安全细节

- 默认 `127.0.0.1` 监听；公网暴露需运维显式改 `WEBUI_BIND` 并加反代鉴权
- 生产 (`WEBUI_ENV=production`) 强制：
  - `AUTH_MODE=oauth`（拒绝 dev）
  - `SESSION_SECRET` 长度 ≥ 32 字节
  - `Secure` cookie + HTTPS only
- 写操作的 csrf 防护：表单提交 + `Origin` 校验；API 走 `X-Requested-With` 头
- 默认拒绝原则：未挂权限注解的写路由 → CI lint 拒绝合入
- 防爆破（OAuth 阶段）：交给 IdP；本仓库不做

## 10. 性能预算

- 任务详情页 SQL 查询 ≤ 5 条，总耗时 < 200 ms
- `metric_snapshot` 走 `(metric_name, ts DESC)` 索引；超 7d 走预聚合视图（TD-013）
- 首页与列表页禁止全表扫描；CI 用 `EXPLAIN` 守护
- crawl_raw 翻页严格 `LIMIT 50 OFFSET ?`，配合 `(task_id, id DESC)` 索引

## 11. 与其它 spec 的接口

- 数据：`data-model.md` §4.1（任务管理）、§4.2（采集运行时）、§4.6（观测）、§4.7（webui 审计 · 本 spec 引入）
- adapter 列表：`infra.adapter_registry.list_all()`（spec: `codegen-output-contract.md`）
- 操作 API：写任务的 `crawl_mode/scope/...` 字段必须与 `infra/crawl/types.TaskSpec` 字段对齐
- 限速操作：调 `infra/http/HostTokenBucket.configure`（admin 页）
- 鉴权：见 §5；OAuth 实施细节在 TD-018 立项时补 rev 3

## 12. 验收点

- 本地用 DevBackend 起 webui，所有 GET 路由 200 ms 内返回
- React 页面可见，不是纯 JSON API；页面能展示 FastAPI `/api/*` 返回的数据
- `cd webui/frontend && npm run build` 成功；FastAPI 可托管 `dist` 后的 `/ui`
- 点进 `/tasks/{id}` 后能看到该 source 的 URL 数量、depth 分布；已抓取链接与跳转链接必须分开展示并各自分页；跳转链接可按 depth 过滤；已有 `crawl_raw` 时同页能看到内容标题/摘要
- 提交一个新任务 → `crawl_task` 行写入 + `created_by` 填充 + `webui_audit` 一行
- 跑完任务后 `/tasks/{id}/items` 能翻 crawl_raw 列表，点开能看到原始 HTML
- `WEBUI_ENV=production` + `AUTH_MODE=dev` 启动时立即失败
- `/admin/*` 路径在 `role=viewer` 时返回 403

## 13. 不在本 spec 范围

- OAuth 接入与 role 映射的实施细节 → **TD-018**，立项时本 spec rev 3
- 移动端适配（v1 桌面浏览器为主）
- 多租户 / 用户体系（暂不需要；交给 IdP）
- 编辑业务规则的 UI（业务规则通过 PR 改代码）
- 实时推送（首版每页 30s 自动刷新即可）
- 改密 / 注册流程（OAuth 后属于 IdP 责任）
- `metric_snapshot` / `alert_history` 体系本身 → `infra-observability.md` + TD-013

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 1 | 2026-04-28 | 初稿（仅监控看板） | — |
| rev 2 | 2026-04-28 | **[breaking]** 重构为"任务后台 + 监控 + 浏览三面合一"；代码落点从 `infra/visualization/` 改为顶层 `webui/`；引入 `AuthBackend` 抽象（DevBackend 默认，OAuthBackend 暂缓 TD-018）；三档角色 + 路由权限矩阵；引入 `webui_audit` 表；MVP 转为实施（替代 TD-014 暂缓状态） | 用户决策 2026-04-28；新增 TD-018 |
| rev 3 | 2026-04-28 | 明确 WebUI 必须提供可见浏览器页面；FastAPI 同时服务页面与 `/api/*`，页面通过本地开源前端库或原生 JS 展示 API 返回的数据；禁止 CDN 运行时依赖，保留无 Node 构建约束 | 用户决策 2026-04-28 |
| rev 4 | 2026-04-28 | 任务详情页升级为 source drill-down：展示 URL 数量、depth 分布、frontier/fetch 状态和已采集内容摘要；新增 `GET /api/tasks/{id}/urls` | 用户决策 2026-04-28 |
| rev 5 | 2026-04-28 | source drill-down 改为紧凑 Ant Design 风格并加入 URL 服务端分页；明确完整 Ant Design Pro/React 版需另开 breaking 计划 | 用户决策 2026-04-28 |
| rev 6 | 2026-04-28 | **[breaking]** 前端从 Jinja/CSS 仿制升级为 React + TypeScript + Vite + Ant Design ProComponents；FastAPI 保留 `/api/*` 并托管 `/ui` SPA | 用户决策 2026-04-28 |
| rev 7 | 2026-04-28 | 任务详情页把已抓取链接与跳转/发现链接拆成两张独立分页表；`GET /api/tasks/{id}/urls` 新增 `kind` 与 `depth` 查询参数，支持查看 `task=1&depth=1` 的跳转链接 | 用户决策 2026-04-28 |
