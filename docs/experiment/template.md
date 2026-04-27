# 实验模板

爬虫实验典型场景：新解析策略、去重阈值调参、AI prompt 迭代、调度权重 A/B。

## 元信息

- **Experiment ID**：`EXP-YYYYMMDD-<slug>`
- **假设**：一句话假设（变量 → 期望效应）
- **Control**：当前线上策略（baseline）
- **Candidate**：待测策略（必须 additive，不破坏 control）
- **范围**：数据切片、host 集合、URL 数量

## 章节

1. Setup —— 数据准备、临时 SQLite、固定 seed
2. Execution —— R1 探索 / R2 精修 / R3 确认
3. Artifact —— `docs/eval-test/<exp-id>.md`：retained-vs-candidate 指标
4. Communication —— 简短结论
5. Closure —— 决策（green/red）；拒绝时删除候选代码

## 硬规则

- 不在生产数据库上跑实验
- candidate 必须 additive，不修改 retained 模型
- 每个实验必须有 retained-vs-candidate 工件，否则不得 promote
