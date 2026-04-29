# Infra 抓取策略

> **版本**：rev 3 · **最近修订**：2026-04-29 · **状态**：active

> 适用：`infra/http/`、`infra/robots/`、`infra/frontier/` 三模块共同遵守的
> 策略契约。所有业务域（`gov_policy/`、未来的 `exchange_policy/` 等）都不
> 得绕过本契约；业务域可在 seeds 中**收紧**默认值，但**不得放宽**安全门槛。
>
> 与 `AGENTS.md` Hard Rules 的对应关系见 §10。

## 1. 适用范围与原则

- 覆盖：限流、重试、robots、反爬识别与降级、出口/代理、紧急止损。
- 原则：**识别 → 降速 / 暂停 / 人工审核**；不绕过、不伪装、不对抗。
- 验证：本 spec 每一条都对应 `infra/harness/` 的可自动化检查或 `tests/` 单元用例。

## 2. 限流策略

### 2.1 三层令牌

| 层级 | 单位 | 由谁控制 | 默认值 | 业务域可覆盖 |
|---|---|---|---|---|
| host 礼貌性 | RPS / burst | host token bucket | `default_rps_per_host = 1.0`、`burst = 2` | 仅可降低（向下） |
| domain 配额 | 总抓取数 | task 创建时设定 | 由 task `max_pages_per_run` 决定 | task 级 |
| 任务预算 | 时间窗、URL 总数 | Frontier | 见 task spec | task 级 |

### 2.2 host 维度公平性

- 多任务共用同一 host 时，按任务优先级 + 老化补偿轮转，避免饥饿。
- 单 host 出现持续 429/5xx 时，公平性让位于退避（见 §3）。

### 2.3 限流分级启动（Warm-up）· 默认开启

**新部署的 adapter / 新 host / canary 流量不得一上来就跑满 `politeness_rps`**。
按 4 级阶梯逐档放开：

| Level | RPS 比例 | 升级条件（同时满足） | 适用 |
|---|---|---|---|
| L0 | × 10%（且至少 0.05 RPS） | 启动级；持续 ≥ 30min 且 4xx/5xx < 1% 且无反爬命中 | 全新 host / canary Stage 0 |
| L1 | × 30% | 持续 ≥ 60min 且 4xx/5xx < 1% 且无反爬命中 | canary Stage 1 |
| L2 | × 60% | 持续 ≥ 120min 且 4xx/5xx < 1% 且无反爬命中 | canary Stage 2 |
| L3 | × 100%（满速） | — | canary Stage 3 |

降级触发（任一命中即退一级 + 重置当前级别计时）：

- 5min 滚动 4xx/5xx 比例 > 5% → 降一级
- 反爬命中 1 次 → 直接降到 L0 + 10min cooldown
- robots 拒绝 → 直接 disable（不在 warm-up 范畴）

何时启用：

| 场景 | warm-up |
|---|---|
| 全新 host 首次抓取 | **强制 L0 起步** |
| Adapter update 合并后（auto-merge canary） | **强制按 canary 阶段对齐 §1 表** |
| 已稳定运行 host 的日常调度 | 跳过 warm-up，直接 L3 |
| 手动触发 `force_full` | 跳过 warm-up（运维兜底；Hard Rules §3 紧急止损仍生效） |

默认参数（环境变量可覆盖，仅向更保守覆盖；不可放宽）：

```
RAMP_UP_LEVEL_FRACTIONS         = [0.10, 0.30, 0.60, 1.00]
RAMP_UP_LEVEL_HOLD_MIN          = [30,    60,   120,  -1]   # -1 = 永驻
RAMP_UP_DEMOTE_4XX5XX_RATIO     = 0.05                       # 5% in 5min 降一级
RAMP_UP_DEMOTE_ANTI_BOT_TO      = "L0+10min cooldown"
RAMP_UP_MIN_RPS_FLOOR           = 0.05                       # 即便 ×10% < 0.05 也按 0.05 跑
```

> 与 `codegen-auto-merge.md` §6 的对应关系：auto-merge 强制 canary，canary
> 强制 warm-up；二者协同保证"自动合并的新 adapter 不会一上线就把 host 打满"。

## 3. 重试策略

### 3.1 重试矩阵

| 响应 | 是否重试 | 备注 |
|---|---|---|
| 200 / 3xx | 否 | 正常 |
| 429 | **是** | `Retry-After` 优先 |
| 5xx（非 robots） | 是 | 同上 |
| 4xx（除 429） | 否 | 含 401/403：进反爬识别（§5），不重试 |
| 网络错误（DNS / TLS / 超时 / 连接重置） | 是 | 同退避公式 |
| robots 5xx | **否** | 视作 complete disallow（§4） |
| 命中反爬信号 | **否** | 进 cooldown（§5），不重试 |

### 3.2 退避公式

```
delay = min(cap, base * 2^attempt) + jitter
```

| 参数 | 默认 |
|---|---|
| `base_sec` | 1 |
| `cap_sec` | 60 |
| `jitter` | uniform(0, 0.5 × backoff) |
| `retry_max` | 3 |

### 3.3 Retry-After 优先级

- 收到 `Retry-After: <seconds>` 或 `<HTTP-date>` 时，**忽略上述公式**，至少等 Retry-After 指定时长。
- Retry-After 同时作用于 host 级 cooldown：该 host 在此期间不再被 frontier 派发。

## 4. robots

- 实现：`infra/robots/`，RFC 9309 基线。
- 缓存 TTL：`robots_cache_ttl = 86400` 秒。
- 状态码语义：

| 取回响应 | 处理 |
|---|---|
| 200 + 可解析 | 按规则执行 |
| 4xx | 视作"无 robots，全允许" |
| 5xx / 网络错误 | **视作 complete disallow**，host 进入 24h 冷却 |
| 解析失败 | 同 5xx |

- User-Agent：包含项目联系信息（邮箱 + 主页 URL）。具体值由配置注入；**不得**伪装为浏览器或其他爬虫。

## 5. 反爬识别与降级

### 5.1 识别信号（任一命中即视作反爬）

| 类型 | 信号 |
|---|---|
| HTTP | 401 / 403、状态正常但极小响应体、Set-Cookie 含 `cf_chl_` / `__cf_bm` 等 WAF 标记 |
| 标题 | "Just a moment"、"verify you are human"、"访问频率限制"、"系统繁忙"、"请输入验证码" 等关键词 |
| DOM | 出现 `iframe[src*=challenge]`、`form[action*=captcha]`、`recaptcha`、`hcaptcha` 等 |
| 重定向 | 跳到登录/验证页（与原 URL 的路径根不同） |

具体特征列表写在 `infra/http/anti_bot_signals.py`，可由各业务域 `harness_rules.compliance_blocklist` 追加（向上累加，不删减）。

### 5.2 命中后动作（仅以下行为合规）

| 动作 | 说明 |
|---|---|
| **host cooldown** | 默认 `cooldown_sec_on_challenge = 600` 秒 |
| **降速** | 把该 host 的 RPS 砍半，直到 24h 内未再触发 |
| **记录工单** | 写入 `infra/observability` 的 `anti_bot_events` 表，含 URL、信号、时间 |
| **暂停 host** | 同一 host 24h 内触发 ≥ N 次（默认 N=3）→ host 进入 `disabled` |

### 5.3 严禁动作（违反即拦截至 PR 合并前）

- 自动调用 captcha solver 服务
- 模拟人类点击/滑块行为
- 伪装真实浏览器指纹（`stealth` 类库 / 篡改 navigator.webdriver）
- 自动登录（即便给了凭证）
- 绕过付费墙

`infra/harness/` 的合规扫描默认禁词列表覆盖以上场景；新增禁词只能加，不能删。

## 6. 出口与代理

- 用途**仅限**：网络稳定性、地域路由、出口信誉管理。
- 同 host 绑定稳定出口；频繁切换 IP 视作对抗信号，禁止。
- 出口选择不依赖站点反爬强度（不为绕过而切）。

## 7. 紧急止损

| 维度 | 阈值 | 动作 |
|---|---|---|
| 全局 5xx 比例 | 10 分钟窗口 ≥ 20% | 全局暂停派发，告警 |
| 单 host 429 + 5xx 比例 | 10 分钟窗口 ≥ 50% | 该 host 暂停 1h |
| 反爬命中频次 | 单 host 24h ≥ 3 | host 进入 `disabled`，开 fix-task |
| Adapter 解析失败 | 连续 ≥ **5** | adapter `disabled`，自动开 fix-task（task_type=`update`） |

止损开关一律**默认开启**；运维可临时关闭单条阈值，但需在 `docs/cleanup-log.md` 记录原因与时长。

## 8. 默认值汇总

```
default_rps_per_host        = 1.0
burst                       = 2
ramp_up_enabled_default     = true
ramp_up_min_rps_floor       = 0.05
retry_max                   = 3
backoff_base_sec            = 1
backoff_cap_sec             = 60
robots_cache_ttl_sec        = 86400
cooldown_sec_on_challenge   = 600
host_disable_threshold      = 3   # 24h 内反爬命中
adapter_disable_threshold   = 5   # 连续解析失败
global_5xx_ratio_threshold  = 0.20
host_4xx_5xx_ratio_threshold= 0.50
emergency_window_sec        = 600
```

所有默认值通过 `infra/http/config.py`（或同等位置）集中暴露；环境变量
覆盖优先于业务域 seeds 覆盖优先于默认值。

## 9. 业务域接口

业务域对本契约的**唯一合法影响通道**：

| 渠道 | 允许的修改 |
|---|---|
| `domains/<context>/seeds/<host>.yaml` | `politeness_rps`（向下）、`max_pages_per_run`、`run_frequency` |
| `domains/<context>/harness_rules.py::compliance_blocklist` | 追加禁词（不可删） |
| `docs/prod-spec/<context>.md` §"反爬执行" | 业务域命中反爬后业务侧的处理（如发停机邮件、关业务订阅等） |

凡涉及"放宽"的修改一律拒绝，CI 守护：
- ruff 自定义规则禁用 `politeness_rps > 默认`
- import-linter 禁止 domain 直接 import `infra/http/anti_bot_signals.py`（只能通过 `harness_rules` 注入）

## 10. 与 AGENTS.md Hard Rules 的对应

| AGENTS.md 条目 | 本 spec 落点 |
|---|---|
| 不绕过保护措施 | §5.3、§9 守护 |
| robots 遵从 | §4 |
| 礼貌性与限速 | §2、§3 |
| 抓取层级顺序（feed → static → API → DOM → render） | 不在本 spec；由 `domains/<context>/parse/` + `render/` 控制 |
| AI 用法 | 不在本 spec；由 `infra/ai/` 与 `domains/<context>/extract/` 控制 |

任何 AGENTS.md 硬规则的变更必须**先**更新本 spec 再改 hard rules，反向同步会被 CI 拦截。

## 11. 验收点

- 单元：见 MVP plan T-20260427-103（HTTP）、T-20260427-104（robots）、T-20260427-105（frontier）
- 端到端：见 M3.5 plan T-20260428-203（harness）、T-20260428-208（注入业务规则）
- 紧急止损：M5（TD-005）启用 `infra/observability` 后补端到端用例

## 12. 不在 v1 范围

- 多 worker 协调下的分布式令牌桶（TD-004 提升后再做）
- 基于 ML 的反爬信号识别（v1 仅规则识别）
- 自动学习 host 健康度调整 RPS（v2）

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 3 | 2026-04-29 | 将无明确站点限速时的默认 host RPS 从 0.5 调整为 1.0；站点 seed 仍只能向下覆盖，`Retry-After`、cooldown、warm-up 规则不变 | `data-model.md` rev 3；`infra/http/token_bucket.py` |
| rev 2 | 2026-04-28 | 新增 §2.3 限流分级启动（warm-up）：4 级阶梯（10%/30%/60%/100%）+ 升降级触发条件 + 默认参数；§8 默认值表追加 ramp-up 相关；为 `codegen-auto-merge.md` canary 提供基础 | — |
| rev 1 | 2026-04-28 | 初稿 | — |
