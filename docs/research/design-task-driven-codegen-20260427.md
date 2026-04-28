# 任务驱动的代码生成爬虫系统 · 设计提案

> 状态：**核心决策已落地**（2026-04-28）。架构与计划已同步。本文保留为
> 设计底稿，正式 spec 待 M3.5 启动时落地为 `docs/prod-spec/codegen-platform.md`（T-20260428-209）。
>
> **已确认决策**：
> 1. 路径：保守（M1–M3 手写沉淀模板，M3.5 起 codegen 接管）→ 已建 `plan-20260428-codegen-bootstrap`
> 2. adapter 路径：`domains/<context>/adapters/<host>.py`（一层文件）
> 3. Task API：**外部独立项目**；本仓库只做消费端（不建 `infra/task_api`、`infra/task_store`）
> 4. task 类型：`create` / `update` / `extend` 三种都做
> 5. OpenCode 模型：参数化（环境变量 / task 字段覆盖）
> 6. 金丝雀阈值：待定（先以环境变量暴露，运行后调）
> 7. 自动 disable：连续 **5** 次解析失败触发

## 1. 核心思路

把"采集器开发"从"码农写"换成"agent 写"。系统呈两个解耦的平面：

- **代码生成面（Code-Gen Plane）**：异步、离线。后台提交 task 后由编码 agent（默认 **OpenCode CLI** 一次性调用）生成站点适配器代码、自测、提 PR、人审、合并。
- **执行面（Execution Plane）**：定时、在线。把已合并的适配器纳入调度，跑数据，写库。

两个平面通过**仓库 main 分支**串联：合入即上线。

```
┌──────── Code-Gen Plane（离线，异步） ────────┐    ┌─── Execution Plane（在线）────┐
│                                                │    │                                │
│  Task API ──→ Task Store                       │    │   Scheduler ──→ Adapter        │
│       ▲          │                             │    │      │           Registry      │
│       │          ▼                             │    │      ▼              │          │
│   后台/前端  Codegen Worker                    │    │   Frontier ←────────┘          │
│              （轮询 pending）                  │    │      │                          │
│                  │                             │    │      ▼                          │
│                  ▼                             │    │   Fetcher ──→ Parser ──→ AI    │
│            隔离 worktree                       │    │                  │              │
│                  │                             │    │                  ▼              │
│                  ▼                             │    │              Dedup/Sink         │
│         CodingAgentBackend                     │    │                  │              │
│           = OpenCodeBackend                    │    │                  ▼              │
│         （subprocess: `opencode run`）         │    │            PolarDB / OSS        │
│                  │                             │    │                                  │
│                  ▼                             │    │                                  │
│         Verification Harness                   │    │                                  │
│                  │                             │    │                                  │
│         gh pr create ──→ 人审 ──→ merge ───────┼────┼─→ 自动注册到 Registry          │
│                                                │    │                                  │
└────────────────────────────────────────────────┘    └─────────────────────────────────┘
        ▲                                                          ▲
        └─────────────────  全部为 infra/  ────────────────────────┘
        domains/<context>/  只提供：业务规格、prompt、schema、黄金用例、生成出的 site adapter
```

**架构原则**：codegen 平台是跨业务域的开发者基础设施，全部下沉到 `infra/`。
业务域只携带 "我要什么、字段长什么样、怎么验证"，不持有"怎么调度 / 怎么生
成 / 怎么注册"。

## 2. 职责切分：infra vs domain

### 2.1 `infra/` 承担（codegen 平台 · 跨域复用）

| infra 模块 | 职责 |
|---|---|
| `infra/task_api/` | HTTP API（`POST /v1/tasks`, `GET /v1/tasks/{id}`, `PATCH .../cancel`），写 Task Store |
| `infra/task_store/` | `crawl_task` 表的 CRUD + 状态机迁移；与 `infra/storage` 共用 dev/prod 切换 |
| `infra/codegen/` | Codegen Worker：轮询 → 抢锁 → 创建 worktree → 喂 prompt → 跑 harness → 提 PR |
| `infra/agent/` | `CodingAgentBackend` 协议；默认实现 `OpenCodeBackend`（详见 §5） |
| `infra/sandbox/` | worktree 隔离 + 文件系统白名单 + 网络白名单 |
| `infra/harness/` | Verification Harness 框架：跑 静态/合规/单元/E2E 检查；规则可由各业务域注入 |
| `infra/adapter_registry/` | 已合并适配器的入口点扫描与按 host 解析 |
| `infra/scheduler/` | 定时调度 + 金丝雀策略 |
| `infra/storage`、`infra/http`、`infra/robots`、`infra/frontier`、`infra/ai` | 既有执行面能力（不变） |

### 2.2 `domains/<context>/` 承担（业务事实）

| 业务侧产物 | 路径示例 |
|---|---|
| 业务规格 | `docs/prod-spec/<context>.md` —— agent 读它知道字段含义 |
| 字段 schema 与 prompt | `domains/<context>/extract/{prompts,schemas}/` —— harness 用它做 e2e 校验 |
| 黄金用例 | `domains/<context>/parse/golden/<host>/` —— harness 用它做单元校验 |
| 业务侧 harness 规则 | `domains/<context>/harness_rules.py` —— 注入到 `infra/harness/`，例：36 字段命中率门槛、合规扫描禁词补充 |
| 生成出的适配器 | `domains/<context>/parse/sites/<host>.py`（codegen 产出） |
| 数据源种子 | `domains/<context>/seeds/<host>.yaml`（task 创建时由 agent 或人写） |

> 关键判定：codegen 模块**不**知道"政策有 36 个字段"，它只知道"业务域注入了
> 一组校验规则，跑过即放行"。这保证 `gov_policy`、`exchange_policy`、
> `oversea_policy` 共用同一套 codegen 平台。

## 3. Task 模型

> **DDL 权威源**：`docs/prod-spec/data-model.md` §4.1（4 主表 + 3 子表 + 1
> 审计表，共 8 张）。本节保留概念描述与字段语义，不再维护字段级伪代码——
> 以避免与 data-model.md 产生双源不一致。

### 3.0 概念分层

| 关注点 | 表 | 写频率 |
|---|---|---|
| 用户提交（少改） | `crawl_task` + 3 子表 | 创建时 + 偶尔编辑 |
| Codegen 过程 | `crawl_task_generation` | 生成期高频 |
| 执行运行时 | `crawl_task_execution` | 调度期高频 |
| 历史审计 | `crawl_task_run` + `crawl_task_audit_event` | 每次跑 / 每次事件 append |



字段级表达详见 `data-model.md`。下面伪代码仅用于说明 task spec 在概念层的
形态，**不是字段权威**：

```
crawl_task {
  task_id            uuid
  status             enum            # 见 §4
  priority           int
  task_type          enum            # create | update | extend
  business_context   str             # gov_policy | exchange_policy | ...
  created_by         str
  created_at         ts
  updated_at         ts

  spec {
    site_url             str         # 例：https://www.ndrc.gov.cn/xxgk/zcfb/
    data_kind            enum        # policy | news | regulation | ...
    scope_description    text        # 自然语言："发改委规范性文件，按时间倒序"
    scope {                          # 结构化作用域（frontier 派发前校验）
      mode               enum        # same_origin | same_etld_plus_one | url_pattern | allowlist
      url_pattern        str?        # 仅 mode=url_pattern
      allowlist_hosts    [str]?      # 仅 mode=allowlist
      follow_canonical   bool        # 默认 true
      follow_pagination  bool        # 默认 true
    }
    expected_fields      [str]?      # 可选；引用业务 spec 字段子集
    sample_urls          [str]?      # 给 agent 当种子；缺省由系统预抓

    # 应用层增量与采集模式（区别于 HTTP 304 传输层，见 infra-resilience.md §1）
    crawl_mode           enum        # full | incremental
    crawl_until          date?       # 仅 full 模式生效；早于此日期的数据停止翻页
    full_crawl_cron      cron?       # 如 "weekly" / "monthly"；NULL = 仅首次全量
    last_full_crawl_at   ts?         # 上次全量完成时间（runner 写）

    constraints {
      max_pages_per_run  int
      run_frequency      cron-expr
      robots_strict      bool        # 默认 true
      politeness_rps     float       # 仅向下覆盖默认；不可放宽
    }
  }

  generation {
    branch             str           # agent/codegen-<task_id>
    worktree_path      str
    pr_url             str
    sandbox_run_id     str
    attempts           int
    last_error         text
    backend            str           # opencode | claude_code | mock
    backend_version    str
  }

  execution {
    adapter_id         str           # 合并后由 registry 分配
    last_run_at        ts
    last_run_status    enum
    canary_until       ts
    heartbeat_at       ts            # worker 5min 更新；stale 阈值见 infra-resilience.md §2.5
  }
}
```

**采集模式决策**（runner 每次执行前判定）：

```
1. 首次运行                              → 强制 full
2. 手动触发 + force_full                  → full
3. 到达 full_crawl_cron 周期               → full
4. 其它日常调度                           → 使用 task.spec.crawl_mode
```

完成 full 时 `last_full_crawl_at = now()`。增量模式由 adapter 内部决定起
点（已有最大页码 / 最新日期），配合 HTTP 304（`infra-resilience.md` §1.1）
进一步减带宽——双层增量。

## 4. 任务状态机

```
   pending
      │ codegen worker 抢锁
      ▼
   claimed
      │ 开 worktree + 分支
      ▼
   drafting          ←── retry（agent 失败可回此状态）
      │ 跑 verification harness
      ▼
   sandbox_test  ──── failed ──→ drafting
      │ harness 全绿
      ▼
   pr_open       ──── reviewer 拒绝 ──→ drafting
      │ tier-1/2 自动通过 § auto-merge-policy / tier-3 人审 + CI 通过
      ▼
   merged
      │ registry 加载
      ▼
   canary_stage_0 (1%)  ──── 失败超阈值 ──→ rolled_back
      │ 1h/4h（按 tier）
      ▼
   canary_stage_1 (10%) ──── 失败超阈值 ──→ rolled_back
      │ 4h/12h
      ▼
   canary_stage_2 (10%) ──── 失败超阈值 ──→ rolled_back
      │ 12h/24h
      ▼
   canary_stage_3 (100%)
      │ 通过门槛
      ▼
   running       ←── 周期任务
      │ task 显式关闭 / 站点下线
      ▼
   completed  /  superseded  /  disabled
```

## 5. 编码 agent 后端：OpenCode CLI

### 5.1 默认后端

默认 backend：**OpenCode CLI（`opencode run` 一次性调用）**。

选择理由：

- 一个 task 起一个子进程，进程退出即干净，不会跨 task 污染上下文
- 沙箱化简单：用 `infra/sandbox/` 把子进程套上文件系统白名单 + 网络白名单
- worker 重启不会丢失"长会话"
- 失败影响半径小：单个子进程崩溃不影响其他在跑 task

### 5.2 抽象协议

`infra/agent/` 定义统一协议，便于换后端：

```python
class CodingAgentBackend(Protocol):
    def run(
        self,
        prompt: str,
        cwd: Path,
        timeout_sec: int,
        env: dict[str, str],
        allowed_paths: list[Path],   # sandbox 写白名单
    ) -> AgentResult: ...

class AgentResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    files_changed: list[Path]
    tokens_used: int | None
```

### 5.3 OpenCodeBackend 实现要点

调用形式（具体 flag 名以 OpenCode 当前版本文档为准，工程实现时由
`infra/agent/opencode_backend.py` 封装；以下是预期形态）：

```python
subprocess.run([
    "opencode", "run", prompt,
    "--cwd", str(cwd),
    "--model", model_id,
    "--max-turns", str(max_turns),
    "--output-format", "json",
],
    timeout=timeout_sec,
    env={**os.environ, **env},
    capture_output=True,
)
```

`stdout` 优先尝试 `--output-format json` 解析；解析失败回退到 `files_changed = git status --porcelain` 推断。

### 5.4 内置备选后端

为防 OpenCode 出问题或不可用，`infra/agent/` 同时带：

- `ClaudeCodeBackend`（`claude -p ...`）
- `MockBackend`（测试 / dry-run）

切换由 `crawl_task.generation.backend` 字段或环境变量 `CODEGEN_BACKEND` 控制。

## 6. Codegen Worker 流程

```
1. 轮询 task_store 取 status='pending' 的最高优先级任务
2. SQL 行锁占位 → status='claimed'
3. git worktree add <wt>/<task_id> agent/codegen-<task_id>
4. 系统侧预抓 5–10 个 sample 详情页，落 <wt>/runtime/cache/<task_id>/
5. 拼装 prompt：
     - AGENTS.md（Hard Rules）
     - docs/prod-spec/<context>.md
     - 现有同 context 适配器作为 few-shot 模板
     - task spec
     - sample HTML 路径
6. CodingAgentBackend.run(prompt, cwd=<wt>, allowed_paths=[
     <wt>/domains/<context>/parse/sites/<host>.*,
     <wt>/domains/<context>/parse/golden/<host>/*,
     <wt>/domains/<context>/seeds/<host>.yaml,
     <wt>/tests/<context>/<host>/*,
   ])
7. 跑 infra/harness（注入 domains/<context>/harness_rules）
   失败 → attempts++，回到 step 5（最多 N=3）
8. 通过 → gh pr create，status='pr_open'
9. 失败超阈值 → status='failed'，last_error 写明
```

## 7. Verification Harness（infra 框架 + domain 规则）

| 检查类型 | 谁定义 | 谁执行 |
|---|---|---|
| 静态 | `infra/harness`（ruff/mypy/import-linter 配置仓库级） | infra |
| 合规扫描禁词 | `infra/harness` 基线 + 各业务域可追加（`harness_rules.compliance_blocklist`） | infra 框架，规则双向 |
| 单元测试 | `domains/<context>/parse/golden/<host>/` 黄金用例 | infra 框架，跑 pytest |
| 端到端 schema 合格率 | `domains/<context>/extract/schemas/<v>.json` | infra 框架，业务域定门槛 |
| robots 实抓 | infra | infra |
| 礼貌性默认值 | infra（基线） + 业务域可降低（不可升高） | infra |

## 8. Human Review Gate
- CI 跑同一 harness 二次确认（防 sandbox 内被绕过）
- 人审清单（PR 模板）：业务字段映射、是否复用 infra、是否引入禁忌依赖

## 9. Adapter Registry 与金丝雀
- 合并后入口点扫描注册：`(host, data_kind, version) → adapter`
- 新合入先进 `canary` 池：低 RPS、独立 sink table、24h 抽检
- 通过后转 `running`，`infra/scheduler` 纳入定时

## 10. 关键风险与开放问题

1. **生成稳定性**：同一 task 多次生成可能不同实现 → 强制同分支 force-update。
2. **重复 host**：task 创建时检查 registry；同 host active adapter 已存在 → `superseded` 或转 `update`。
3. **凭证隔离**：sandbox 不持有生产凭证；e2e 测试只用 fixture。
4. **PR 风暴**：限制 `max_concurrent_codegen=2~4`；其余排队。
5. **解析器衰老**：站点改版后 e2e 失败 → 自动开 fix-task（`task_type=update`）。
6. **agent 越权**：`infra/sandbox/` 文件系统白名单只允许写 §6 step 6 列出的路径。
7. **OpenCode 版本飘移**：`crawl_task.generation.backend_version` 留痕，回归时可锁定。
8. **多业务域共存**：`task.business_context` 决定 prompt 模板与 harness 规则注入哪个 domain；codegen 平台本身不需要改动。

## 11. 与现有 MVP 计划的关系

两条路径供选择：

### 11.1 保守路径（推荐）
- M1–M3 仍然**手写**国务院 + 8 部委适配器，沉淀至少 9 个高质量样本作为 OpenCode 的 few-shot 模板，并把 `infra/` 执行面打磨好。
- M3.5 起新增子计划 `PLAN-codegen-bootstrap`：依次建设 `infra/{task_api,task_store,codegen,agent,sandbox,harness,adapter_registry,scheduler}`，最后用一个"复刻已存在部委"任务做端到端验证。
- M4（31 省地方）由 codegen 接管。地方政府门户高度模板化，正是 agent 的甜点。

**优点**：MVP 不押注外部 agent 调通；手写代码即模板。
**缺点**：手写部分多用 5–6 周。

### 11.2 激进路径
- MVP 直接做 codegen 框架，国务院手写一份当模板，部委起就让 agent 跑。

**优点**：早 6 周进入"自动化"。
**缺点**：调通 codegen 涉及 sandbox、harness、agent 鉴权、CI 整合，并非"接 API 就好"；M1 风险高。

## 12. 若采纳本方案需要回头改的清单

只有用户拍板后才动：

- `docs/architecture.md`：第 1 节"分层"扩为"双平面"；第 2 节目录结构补 `infra/{task_api,task_store,codegen,agent,sandbox,harness,adapter_registry,scheduler}`；第 3 节依赖规则加 "agent 只能写沙箱白名单路径"；第 4 节关键决策加 "默认编码 agent = OpenCode CLI"。
- `docs/prod-spec/domain-gov-policy.md`：§8 加入 "harness_rules"、"golden/" 目录；新增 §10 描述 task spec 在本业务域下的字段要求与默认值。
- `docs/exec-plan/active/plan-20260427-mvp-policy-crawler.md`：按选择的路径调整 M1–M3 任务，或新增 M3.5 子计划。
- `docs/exec-plan/active/roadmap-policy-crawler.md`：插入 codegen 里程碑。
- `docs/infra-overview.md`：补入 codegen 平台模块清单。
- `docs/domains-overview.md`：说明 "domain 注入 harness_rules + golden + prompt + schema"，不持有调度/生成逻辑。

## 13. 待用户决策的问题

1. **路径**：保守（推荐）还是激进？
2. **task 提交入口**：先做最小 HTTP API（FastAPI 单文件），还是直接对接公司现有后台？
3. **adapter 文件归属**：放在 `domains/<context>/parse/sites/<host>.py`（同业务域），还是按 host 反向独立 `adapters/<host>/`（跨业务域复用）？建议前者。
4. **task 类型**：`create` / `update` / `extend` 三种是否都做？
5. **金丝雀策略**：N 次成功的 N 取多少？默认 7 天 + 100 条无错？
6. **失败回退**：连续 K 次解析失败自动 disable adapter + 开 fix-task？K=?
7. **OpenCode 模型默认值**：`anthropic/claude-sonnet-4-6` 是否合适？任务级是否允许覆盖？
