# <评估标题>

> **类型**：`experiment-artifact | acceptance-report | regression-check | adversarial-case`
> **关联**：Plan/Task/Experiment ID（如 `PLAN-...` / `T-...` / `EXP-...`）
> **作者**：Evaluator
> **日期**：YYYY-MM-DD
> **判定**：`green | red | partial`（partial 必须在 §6 写出阻塞项）

## 1. 背景与目的

一句话陈述：本评估要回答什么问题、为什么现在做。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | 例：当前线上 prompt v1；当前 dedup 阈值 |
| Candidate（候选） | 例：prompt v2；阈值由 0.85 降到 0.80 |
| 数据切片 | 例：国务院文件库 100 条；时间窗 2026-04 整月 |
| 评估口径 | 列出本次使用的指标（与 §3 / §4 表头一致） |
| 复现命令 | 例：`uv run scripts/eval_prompt.py --task T-... --snapshot test_xxx.db` |
| 临时 DB 路径 | `runtime/db/test_<task_id>_<ts>.db`（来源说明） |

> 控制组与候选组**必须**使用同一 DB 快照（experiment 硬规则）。

## 3. 度量结果 · 聚合

| 指标 | Control | Candidate | Δ | 备注 |
|---|---|---|---|---|
| 例：schema 合格率 | 88.0% | 93.5% | +5.5pp | 30 条样本人工抽查 |
| 例：关键 6 字段联合准确率 | 91.0% | 95.7% | +4.7pp | 同样本 |
| 例：单页平均 token 用量（输出） | 410 | 462 | +12.7% | 由 LiteLLM 拉数 |

## 4. 度量结果 · 按切片

按需选切：按 host / 按发文层级 / 按月 / 按数据种类 / 按解析失败 vs 正常等。
每张切片表与 §3 同列结构。

## 5. 异常案例

列出 ≤ 5 个最具代表性的失败 / 退化 / 边界用例，标记 URL/文件/原因/期望
行为，便于复现与排错。

## 6. 结论与决策

- **判定**：`green | red | partial`（与首部一致）
- **理由**：明确依据上面哪几条指标作出判定；不引入未经评估的假设
- **风险**：候选可能引入但未被覆盖的潜在副作用
- **partial 阻塞项**（仅当判定 = partial 填写）

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 是否开新 task | task ID / 新 plan 引用 |
| 是否开 fix-task（站点退化） | 调用 `infra/version_guard` 自动开单或人工 |
| 关闭哪些 task / plan | 引用 ID |
| 候选若被拒（red），是否清理候选代码 | 必须；分支 / PR 处理记录 |

## 修订历史

工件原则上一次性产出。若评估后补数据 / 修正指标，追加一行说明改动原因
（例：发现 sink 失败导致 5 条样本被错误计入 candidate fail）。

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | YYYY-MM-DD | 初版 |
