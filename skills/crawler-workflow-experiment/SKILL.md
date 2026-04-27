---
name: crawler-workflow-experiment
description: 当任务属于 xiniu-crawler 仓库的实验流时使用。爬虫实验典型场景包括：新解析策略、去重阈值调参、AI prompt 迭代、调度权重 A/B；候选必须 additive，必须在临时 DB 上跑，并以 retained-vs-candidate 工件收尾。
---

# Crawler Workflow · 实验环路

适用于走实验环路的工作：

`Hypothesis -> Setup -> Execution -> Artifact -> Communication -> Closure`

`AGENTS.md` 为权威；本 skill 只是这条环路的安全执行说明。

## 首读顺序

按顺序加载：

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/experiment/`、`docs/eval-test/` 下相关文件，以及涉及的 domain 路径

## 何时路由到这里

任务是探索性的策略/参数迭代，而不是正常功能交付，常见情形：

- 站点适配器的新解析策略（如先静态后接口拦截）
- 解析层去重阈值（联合键、simhash 距离）调参
- AI 抽取 prompt 与字段 schema 迭代
- Frontier 优先级权重、host_score 系数 A/B
- 渲染判定信号阈值（DOM 文本密度、空壳页判定）调整

如果工作已批准走正常交付，回到 `crawler-workflow-execution`。

## 实验流程

1. `Hypothesis`：在 `docs/experiment/` 创建/更新实验文档，定义假设、retained 控制组、candidate 候选组，以及评估指标。
2. `Setup`：开隔离实验分支或 worktree；从主检出同步 `.env`；在主检出共享 DB 根目录 `/Users/wangjisong/xiniu/code/xiniu-crawler/runtime/db/` 下建一个 `test_<task_id>_<timestamp>.db` 临时库（必要时由生产/线下 DB 完整文件级拷贝得到）。
3. `Execution`：仅实现 additive 候选，并在临时 DB 上跑实验。
4. `Artifact`：在 `docs/eval-test/` 写下 retained-vs-candidate 报告，覆盖核心指标的 aggregate 与切片对比。
5. `Communication`：结论稳定后做简短沟通；本期暂不接入邮件，沟通形式由用户指定。
6. `Closure`：当周期内收尾分支：
   - `Green`：把候选实现转入正常交付环路，最终分支状态合入 `main`，再清理实验分支/worktree。
   - `Red`：保留实验工件，但合入前删除/回退被拒绝的候选代码；之后把文档/任务状态收尾合入 `main`，并清理分支/worktree。
   - `运行时清理`：把陈旧 `runtime/db/test_*.db` 修剪到至多最近 5 份；活跃 worktree、当前分支、`in_progress` 任务、用户显式指定保留的 DB 不计入清理。

## 爬虫实验通用指标

视实验类型选择，至少覆盖其中相关项：

- 解析策略：字段抽取召回率、JSON schema 合格率、单页解析耗时
- 去重：同一政策跨源命中数、错合并率（误去重）、漏去重率
- AI prompt：36 字段中关键字段（标题、发文字号、发布日期、发文层级、行政区划、政策种类）的准确率与稳定性
- 调度：完成 N 个任务的总时延、host 维度 429/5xx 比例、Frontier 平均等待
- 渲染：渲染调用率、误判率（不需渲染却调用）、漏判率

## 角色分工

- `Planner`：负责实验假设、arm 定义、`docs/experiment/` 中的成功门槛
- `Generator`：负责 additive 候选实现、临时 DB 准备、实验执行
- `Evaluator`：负责 retained-vs-candidate 工件、pass/fail 判断、记录结论

跨仓库使用时按"产物归属"映射角色，不按标题字面。

## 硬规则

- 实验必须 additive。不得就地修改 retained 生产路径。
- 实验只在主检出共享 DB 根 `/Users/wangjisong/xiniu/code/xiniu-crawler/runtime/db/` 下的临时 DB 上跑，不得写生产库（PolarDB）。
- 专用 worktree 不另建持久 `runtime/db/` 树，复用主检出 DB 根并在其下创建有界 `test_*.db` 快照。
- 专用 worktree 在跑 env-backed 命令前，必须先从主检出同步 `.env`。
- 控制组与候选组使用同一 DB 快照。
- 没有 `docs/eval-test/` 下的 retained-vs-candidate 工件，实验不算结束。
- 被拒绝（`Red`）的候选代码不得留在 `main` 的最终合并状态里。
- `Green` 不是直接合并许可。先把候选并入正常 `Spec -> Plan -> Task -> Code -> Evidence` 流，再合并最终被接受的分支状态。
- 实验文档没写下结论，实验不算结束。
- 实验线没收尾（沟通完成、最终分支状态合入 `main`、分支/worktree 清理完毕或被显式标记为阻塞），实验不算结束。

## 默认姿态

- 写代码前先把假设写下来。
- 候选逻辑保持隔离，使其可被干净 promote 或 discard。
- 把 `Red` 当作知识沉淀，不当作失败。
- 沟通完成后立即收尾该实验线，不要把已合并/可合并的实验分支、worktree、堆积的 `test_*.db` 留在那里。
