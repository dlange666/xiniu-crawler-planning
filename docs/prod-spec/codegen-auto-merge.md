# 自动合并策略 · 跳过人审的安全网

> **版本**：rev 1 · **最近修订**：2026-04-28 · **状态**：active
> **实施状态**：M3.5 codegen-bootstrap 阶段实施（关联 plan-20260428-codegen-bootstrap，
> 新增 T-212~216）

> 本 spec 定义**跳过人审环节**时的多层防御：分级范围闸口（L1）、Harness
> 加压（L3）、渐进金丝雀 + 自动回滚（L6）、审计链路（L8）。
>
> 与 `codegen-output-contract.md` 互补：那个 spec 管"agent 写出的 adapter
> 长什么样"，本 spec 管"什么情况下能放它合入 main"。
>
> **不**实现"多 agent 交叉（L4）"与"影子运行（L5）"——这两项作为后续优化项，
> 按 false-positive 数据决定是否引入。

## 1. 风险模型

人审通常挡住 5 类风险，自动化必须替换：

| 风险 | 防线 |
|---|---|
| 合规绕过（captcha solver / 登录绕过） | L1 sandbox 写白名单 + L3 禁词扫描 |
| 结构污染（动 infra / 别的业务域） | L1 sandbox 写白名单 |
| 业务字段错配（语义错） | L3 加压 + L6 canary 数据对账 |
| 隐性 breaking change | L1 限制可改路径 + L6 现役 host 回归 |
| 运营风险（一上线打挂 host） | L1 ramp-up RPS（warm-up）+ L6 流量分档 |

## 2. L1 · 分级范围闸口（Tier）

按"PR 触达的路径"自动判定 tier，不同 tier 走不同合并路径。

| Tier | 触达路径白名单 | 合并方式 | Harness 门槛 | Canary |
|---|---|---|---|---|
| **1 自动** | 仅 `domains/<ctx>/adapters/<host>.py` + `domains/<ctx>/golden/<host>/*` + `tests/<ctx>/adapters/test_<host>.py` + `domains/<ctx>/seeds/<host>.yaml`，且 host 为**新增** | 全自动 | §3 全部 | §4 三档 |
| **2 半自动** | tier-1 路径但 host 已存在（update 已有 adapter）；或 `domains/<ctx>/extract/prompts/*`、`domains/<ctx>/harness_rules.py` | 全自动；强制 24h canary | §3 全部 + 现役回归（§3.6） | §4 三档加慢 |
| **3 人工** | 触达 `infra/`、`docs/prod-spec/*`、`docs/architecture.md`、`AGENTS.md`、其它业务域 | **永远人工** | — | — |

### 2.1 Sandbox 写白名单（L1 强执行）

`infra/sandbox/` 按 tier 提供不同的写白名单。**tier-3 路径直接不在 agent
可写名单中**——agent 想都不能想。

```python
TIER_WRITE_ALLOWLIST = {
  "tier1_create_host": [
    "domains/<ctx>/adapters/<host>.py",            # 仅新增
    "domains/<ctx>/golden/<host>/",
    "tests/<ctx>/adapters/test_<host>.py",
    "domains/<ctx>/seeds/<host>.yaml",
  ],
  "tier2_update_host": [
    # 同 tier1，但允许覆盖已有 host 文件
    *,
    "domains/<ctx>/extract/prompts/",
    "domains/<ctx>/harness_rules.py",
  ],
  # tier3 不开放给 agent
}
```

### 2.2 Tier 判定时机

- **PR 创建时**由 codegen worker 计算 tier（基于 task 类型 + 待写文件清单）
- 写到 `crawl_task.generation.tier` 字段，全链路使用
- 任意 tier-3 路径出现在 PR diff 中 → 直接拒绝（agent 越权 = 失败）

## 3. L3 · Harness 加压门槛

`codegen-output-contract.md` §5 是**最低门槛**；本 spec **加严**：

| 检查项 | codegen-contract §5 | 本 spec（自动合并） |
|---|---|---|
| Golden HTML 数 | ≥ 5 | **≥ 10** |
| E2E 写库行数 | ≥ 1 | **≥ 20** |
| schema 合格率 | 100%（小样本） | **≥ 98%（≥ 20 条）** |
| 关键字段命中率 | 业务域定 | **≥ 99%（关键字段由业务域 harness_rules 声明）** |
| 合规扫描禁词 | 基线 | **基线 + 30+ 条扩展**（见 §3.5） |
| robots 实抓 | ✓ | ✓ |
| **现役回归（仅 tier-2）** | — | **§3.6** |

### 3.1 ~~3.4 同 codegen-output-contract.md 略

### 3.5 扩展禁词清单（合规扫描）

在 codegen-contract 基线之上追加（按风险类别）：

| 类别 | 禁词样例 |
|---|---|
| Captcha 绕过 | `2captcha`, `anti-captcha`, `capsolver`, `recaptcha-solver`, `funcaptcha` |
| 浏览器伪装 | `undetected-chromedriver`, `playwright-stealth`, `selenium-stealth`, `puppeteer-stealth` |
| 指纹伪装 | `pyppeteer-stealth`, `fingerprint-suite`, `navigator.webdriver = false`, `webdriver-manager` |
| 自动登录 | `username=...password=`, `session.post.*login`, `OAuth2.*automate` |
| 协议绕过 | `urllib.request.urlopen.*verify=False`, `ssl._create_unverified_context`（除非显式注释允许） |
| 反爬识别绕过 | `bypass`, `evade`, `humanize-mouse`, `simulate-typing` |

完整列表维护在 `infra/harness/blocklist.yaml`。新增禁词只能加不能删；删除
需走 tier-3 PR。

### 3.6 现役回归（tier-2 强制）

tier-2 触达已存在的 adapter / prompt / harness_rules 时，**必须**对所有
受影响 host 跑一次 golden 与 E2E：

- 跑 `domains/<ctx>/golden/*/` 全集（不只是新动的 host）
- 任意 host 解析输出与黄金 JSON 不匹配 → 拦截
- 跑 dev profile 下"近 7 天 sample 100 条"复刻，schema 合格率 ≥ 95% 才放行

## 4. L6 · 渐进 Canary 与自动回滚

合并后**不直接全量**，按 4 档分流：

```
合入 main → 0% → 1% → 10% → 100%
            │     │      │
            │     │      └─→ Stage 3：观察 ≥ X 小时
            │     └─→ Stage 2：观察 ≥ X 小时
            └─→ Stage 1：观察 ≥ X 小时
```

每档观察期与失败阈值（按 tier 区分）：

| 阶段 | tier-1 观察期 | tier-2 观察期 | 升档失败阈值（任意一项命中即回滚）|
|---|---|---|---|
| Stage 0 → 1（1%） | 1h | 4h | 5xx 比例 > 5% / 反爬命中 ≥ 1 / 解析失败率 > 历史 P95 + 20pp |
| Stage 1 → 2（10%） | 4h | 12h | 同上更严：5xx > 2% / 反爬命中 ≥ 1 / 解析失败 > P95 + 10pp |
| Stage 2 → 3（100%） | 12h | 24h | 5xx > 1% / 反爬 ≥ 1 / 字段命中 < 95% |

### 4.1 自动回滚

任意阶段触发 → 立即：

1. `crawl_task.execution.last_run_status = 'rolled_back'`
2. `adapter_registry` 把当前 adapter 设为 `disabled`，回退到上一个 active 版本
3. 调外部 task 项目接口创建 fix-task（`task_type=update`），把回滚原因写入 `last_error`
4. IM webhook 报警（§5）

### 4.2 影子流量来源

Canary 的"流量"来自：
- tier-1（new host）：从 frontier 派发的真实任务，按比例切到新 adapter
- tier-2（update host）：从 frontier 拷贝一份镜像流量给新 adapter，结果**只入 sink dev table**做对比，不影响生产；阶段 2/3 才真正切流量

> "影子运行"语义在 tier-2 Stage 0–1 自然实现；本 spec 不单独建 L5 模块。

## 5. L8 · 审计与告警链路

每次自动合并 / 升档 / 回滚 都打 IM webhook（沿用 `infra-observability.md` §7 的
通道），即使 observability 整体暂缓，本 spec 也要求**最小审计链路**：

| 事件 | webhook payload 必含 |
|---|---|
| auto-merge | task_id / tier / branch / pr_url / harness_report_uri |
| canary 升档 | task_id / from_stage / to_stage / metrics 摘要 |
| 自动回滚 | task_id / stage / 原因（5xx 比例 / 反爬 / 解析失败） / fix_task_id |
| tier-3 拦截 | task_id / 触达的禁忌路径 / agent 输出摘要 |

回放链路（数据 + 链接全部入 `crawl_task.audit_log` JSON 字段）：

```
PR url → harness 报告 → agent stdout/stderr → sandbox 文件树 diff
       → canary 各档指标快照 → 回滚记录（如有）
```

任何一项缺失 → 该 task 不允许进入 tier-1 自动合并。

## 6. 限流分级启动（warm-up）

**新合并的 adapter 不得一上来就跑满 `politeness_rps`**，详见
`infra-fetch-policy.md` §3 ramp-up。本 spec 在 canary 各阶段强制启用：

| Canary 阶段 | RPS 比例 |
|---|---|
| Stage 0（1%） | warm-up Level 0：default_rps × 10% |
| Stage 1（10%） | warm-up Level 1：× 30% |
| Stage 2（10%）满负载稳定 | warm-up Level 2：× 60% |
| Stage 3（100%） | warm-up Level 3：满速 |

ramp-up 升级条件由 fetch-policy 控制；本 spec 仅声明"canary 必须强制
warm-up"。

## 7. 与其他 spec 的关系

| 关系 | spec |
|---|---|
| Adapter 文件结构 / 默认 sink schema / harness 最低门槛 | `codegen-output-contract.md` |
| Sandbox 白名单（按 tier 提供） | `infra-deployment.md` + `codegen-output-contract.md` |
| 限流 warm-up | `infra-fetch-policy.md` §3（本 spec 调用方） |
| 审计 webhook 通道 | `infra-observability.md` §7 |
| 解析失败率 / 反爬事件指标 | `infra-observability.md` §3 |

## 8. 不在本 spec 范围

- **L4 多 agent 交叉验证**：列入 TD-017，按 false-positive 数据再启用
- **L5 独立影子运行**：tier-2 canary Stage 0 已隐式覆盖；不另设
- 完整审计链路（多日存档、可视化）：等 observability 整体启用（TD-013）后衔接
- 跨业务域批量 hostfix：当前一次只动一个 host

## 修订历史

| 修订 | 日期 | 摘要 | 关联 |
|---|---|---|---|
| rev 1 | 2026-04-28 | 初稿 —— 跳过人审的 4 层防御：L1 分级闸口（tier 1/2/3）+ L3 加压门槛（golden 10 / E2E 20 / schema 98% / 关键字段 99% / 30+ 禁词）+ L6 三档 canary + L8 审计 webhook；canary 强制 warm-up | — |
