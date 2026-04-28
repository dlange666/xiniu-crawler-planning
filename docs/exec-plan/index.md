# docs/exec-plan/ —— 执行计划索引

存放仓库的"做什么、怎么做"——计划与路线图。

## 子目录与流转

```
active/      ← 当前在做的 plan、ROADMAP                                    (扫描入口)
deferred/    ← 已设计但暂缓实施的 plan（链回 tech-debt-tracker.md）        (扫描入口)
archive/     ← 已完结的 plan，按 ISO 周归档：archive/YYYY-Www/             (扫描入口)
completed/   ← 历史遗留兼容；新 plan 不进这里                              (legacy)
```

流转：

```
新计划起草       →  active/PLAN-YYYYMMDD-<slug>.md
计划全部 green   →  archive/YYYY-Www/PLAN-...md（按合入周归档）
计划暂缓         →  deferred/PLAN-...md + tech-debt-tracker.md 登记 TD
```

## 命名约定

- **PLAN-YYYYMMDD-`<slug>`.md**：原子任务计划。日期是创建日期。
- **ROADMAP-`<scope>`.md**：跨多个 plan 的总路线图（不带日期）。
- **tech-debt-tracker.md**：技术债登记表（顶层单文件）。
- **template.md**：新 plan 的起手模板。

## 当前索引（active/）

| 文件 | 类型 | 状态 | 关联 |
|---|---|---|---|
| `roadmap-policy-crawler.md` | 路线图 | M0–M8 全周期 | 全局 |
| `plan-20260427-mvp-policy-crawler.md` | MVP 计划 | active | M0–M3，14 个原子任务 |
| `plan-20260428-codegen-bootstrap.md` | 代码生成平台 | active | M3.5，16 个原子任务 |

## deferred/

| 文件 | 暂缓原因 | 提升触发 |
|---|---|---|
| `plan-20260428-observability-bootstrap.md` | TD-013：MVP 阶段无可观测性需求 | MVP 跑稳后 |

## tech-debt-tracker.md

非紧急债务在此登记，必须由 `Planner` 显式提升后才进入活跃。详见文件本身
（TD-001..017）。

## 何时进入 archive/

- 计划下所有任务 `completed`
- 必要的评估证据已写入 `docs/eval-test/`
- 关联 spec 的成功标准已满足

按合入周（ISO week）建子目录：`archive/2026-W18/`、`archive/2026-W19/`。
