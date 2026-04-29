# Codegen Feedback Loop Evaluation

> **类型**：`acceptance-report`
> **关联**：`plan-20260429-codegen-feedback` / `T-20260429-901` / `T-20260429-902` / `T-20260429-903` / `T-20260429-904` / `T-20260429-905`
> **验证 spec**：`codegen-output-contract.md` §3, §3.1, §5, §6
> **作者**：Evaluator
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

本评估验证 codegen 平台是否已把最近 source codegen 暴露的问题固化为确定性能力：red 自动反馈迭代、覆盖型 golden、脚本污染 audit、detail URL scope gate，以及更明确的 opencode 收口提示词。

## 2. 实验设计

| 项 | 内容 |
|---|---|
| Control（基线） | wrapper 只跑一次 opencode + 纯数量 golden gate + body 长度/metadata audit |
| Candidate（候选） | wrapper red feedback 迭代、覆盖型配对 golden、script_noise audit、detail_url_pattern gate、prompt/spec 强化 |
| 数据切片 | 单元测试与 runner wrapper 逻辑；不重新采集外部 source |
| 评估口径 | ruff、py_compile、局部 pytest、全量 pytest、spec/task JSON 校验 |
| 复现命令 | 见 §3 |
| 临时 DB 路径 | 无；本次未新增运行时 DB 工件 |

## 3. 度量结果 · 聚合

| 指标 | Control | Candidate | Δ | 备注 |
|---|---|---|---|---|
| red 后自主迭代 | 无 | 最多 3 轮 `.codegen-feedback.md` 回灌 | +3 轮 | 回灌失败 gate 输出、audit 样本、pattern miss |
| golden gate | 文件数 ≥5 | 覆盖型配对：≥1 list、≥3 detail、分页页如适用 | 质量提升 | 防止聚合 JSON 凑数 |
| audit 文本污染 | 无 | `script_noise_rate_max=0` 默认 gate | 新增 | 防止 JS 噪声撑 body 长度 |
| detail URL scope | 依赖人工 review | live smoke 入库 URL pattern match ≥95% | 新增 | 防止导航/社媒链接误入 |
| SourceMetadata prompt | 隐含 | 明确 `SourceMetadata(raw={...})` + `.raw` 测试读取 | 明确化 | 修复常见 red 来源 |

复现命令：

```bash
uv run python -m json.tool docs/task/active/task-codegen-feedback-2026-04-29.json >/dev/null
uv run python -m py_compile scripts/run_codegen_for_adapter.py scripts/audit_crawl_quality.py
uv run ruff check scripts/run_codegen_for_adapter.py scripts/audit_crawl_quality.py tests/infra/test_codegen_task_runner.py tests/infra/test_audit_crawl_quality.py
uv run pytest tests/infra/test_codegen_task_runner.py tests/infra/test_audit_crawl_quality.py -q
uv run pytest tests/ -q
```

结果：

```text
ruff: All checks passed
pytest tests/infra/test_codegen_task_runner.py tests/infra/test_audit_crawl_quality.py -q: 18 passed
pytest tests/ -q: 124 passed
```

## 4. 度量结果 · 按切片

| 切片 | 结果 | 说明 |
|---|---|---|
| wrapper feedback | PASS | `write_feedback_prompt` 单测覆盖失败 gate 输出、SourceMetadata 提醒、short body sample |
| golden gate | PASS | 单测覆盖合法覆盖样本与缺分页样本 red |
| audit quality | PASS | 单测覆盖 `script_noise_rate` 默认失败 |
| prompt/spec | PASS | pipeline 与 `codegen-output-contract.md` rev 14 同步 |

## 5. 异常案例

| 案例 | 处理 |
|---|---|
| opencode 自报 green 但 wrapper red | wrapper 现在可回灌真实 gate 失败证据并继续迭代 |
| 短正文样本来自非业务 URL | prompt 要求分析 audit sample 并在 adapter scope/pattern 过滤 |
| 正文夹带 JS 变量 | audit 默认以 `script_noise_rate_max=0` 卡住 |
| golden JSON 聚合凑数 | gate 要求 HTML/JSON 同名配对和覆盖类型 |

## 6. 结论与决策

- **判定**：`green`
- **理由**：代码、测试、spec、pipeline 均已同步，局部与全量验证通过。
- **风险**：`detail_url_pattern` gate 依赖 adapter 的 pattern 质量；pattern 写得过宽仍需 audit short body 与人工 review 兜底。

## 7. 后续行动

| 事项 | 落点 |
|---|---|
| 开 PR | `agent/infra-20260429-codegen-feedback` |
| 后续实测 | 下一个 source codegen 自动触发 red feedback 行为 |
| 是否需要新 task | 暂无；如多个 source 重复出现同类 pagination fallback，再提升 infra helper |

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版：codegen feedback loop 验收 green |
