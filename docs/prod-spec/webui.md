# Webui · 任务后台 + 采集监控 + 结果浏览（自建轻量看板）
> **版本**：rev 2 · **最近修订**：2026-04-28 · **状态**：active
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
> 三件事共用一个 FastAPI 应用，靠路由分组而不是分仓。本 spec 给出**单进程内嵌
> Web 服务 + 服务端渲染 + 外部 OAuth**（MVP 用 DevBackend 占位）的最小方案。

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
浏览器 ─→ FastAPI（同 crawler 进程或独立进程，二选一）
            ├─ Jinja2 模板 → HTML（SSR）
            ├─ /api/*    → JSON ─→ Chart.js 客户端绘图
            └─ 静态资源  → Chart.js（本地静态，不走 CDN）
            │
            └─→ 读 PolarDB / SQLite（业务表 + 观测表）
```

| 组件 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | 已是 crawler 默认依赖，不引入新栈 |
| 模板 | Jinja2 | 标准、无依赖 |
| 图表 | Chart.js（本地静态） | 单文件，零构建 |
| 鉴权（MVP） | `DevBackend`（env 注入用户名 + role，免登） | 本地 / 内网受信环境足够 |
| 鉴权（生产） | OAuth 2.0 + OIDC（Authorization Code + PKCE）+ 签名 cookie | 不在本仓库存凭据；TD-018 |
| 静态资源 | FastAPI 自带 StaticFiles | 不引入 CDN/Nginx |
| Session | `starlette.SessionMiddleware`（签名 cookie，无服务端 session 存储） | 多副本无状态 |

**没有**：Vue/React、TS/前端构建、Webpack、单独的 Node 服务、Grafana、Tableau、本地密码库、Redis session。

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
│   ├── tasks.py               [A] /tasks*
│   ├── monitor.py             [B] /、/monitor、/hosts、/adapters、/api/*
│   ├── browse.py              [C] /tasks/{id}/items、/browse*
│   └── admin.py               [A] /admin/*
├── stores/                    数据访问层（只读 SQL，与 infra.storage 分离）
│   ├── task_store.py          crawl_task CRUD
│   ├── progress_store.py      url_record / fetch_record 聚合
│   └── audit_store.py         webui_audit 写入
├── templates/
│   ├── _base.html             共用 nav / 鉴权状态 / role 显示
│   ├── tasks/                 任务列表 / 详情 / 提交表单
│   ├── monitor/
│   ├── browse/
│   └── errors/                401/403/404/5xx
└── static/
    ├── chart.min.js
    └── webui.css
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

| 路径 | 内容 |
|---|---|
| `/` | 首页：在跑任务卡片（进度条、最近 1h 抓取量、当前 AI 成本）；本月 AI 成本汇总；OSS 用量趋势（成本类暂依赖 TD-013） |
| `/tasks` | 列表：状态 / business_context 筛选；分页；显示 `created_by` |
| `/tasks/new` | 提交表单：seed_host / entry_urls / strategy / max_depth / scope / RPS |
| `/tasks/{id}` | 详情：上半屏参数 + 操作（cancel / pause / 复制启动命令）；下半屏漏斗 + 时序图 + 失败列表 |
| `/tasks/{id}/items[/{n}]` | crawl_raw 翻页 + 单条预览（标题、body、attachments、原始 HTML 链接） |
| `/monitor` | 全局监控（跨任务） |
| `/hosts[/{host}]` | host 列表 / 详情（依赖 TD-013） |
| `/adapters` | 已注册 adapter 列表（`infra.adapter_registry.list_all()`），含 `last_verified_at` / `render_mode` |
| `/alerts` | 告警历史（TD-013） |
| `/spend` | LiteLLM 成本（TD-013） |
| `/admin/*` | 管理操作（admin 角色） |

### 7.2 API

| 端点 | 返回 | 鉴权 |
|---|---|---|
| `GET /api/tasks` | 任务列表（分页） | viewer |
| `GET /api/tasks/{id}/timeseries?metric=...&from=...&to=...` | 单任务指标时间序列 | viewer |
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
