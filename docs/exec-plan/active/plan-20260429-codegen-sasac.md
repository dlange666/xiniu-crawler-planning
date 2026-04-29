# Plan: codegen-sasac

> **版本**：rev 1 · **最近修订**：2026-04-29 · **状态**：active

## 关联 spec

- `docs/prod-spec/codegen-output-contract.md`
- `docs/codegen-pipeline.md`

## 目标

| 项 | 值 |
|---|---|
| business_context | `gov_policy` |
| data_kind | `policy` |
| host | `www.sasac.gov.cn` |
| entry URL | `http://www.sasac.gov.cn/n2588035/n2588320/index.html` |
| scope_mode | `same_origin` |
| render_mode | `direct` |

## 原子任务

| ID | 任务 | 验收 |
|---|---|---|
| T-20260429-701 | 站点探查 & 分析 | probe verdict |
| T-20260429-702 | 实现 adapter | registry 通过 |
| T-20260429-703 | 实现 seed | YAML 有效 |
| T-20260429-704 | 采集 golden 样本 | >=5 HTML + >=5 JSON |
| T-20260429-705 | 实现单元测试 | pytest 通过 |
| T-20260429-706 | Live smoke | raw_records >= 1 |
| T-20260429-707 | Audit | 退出码 0 |
| T-20260429-708 | 写 eval | green/red/partial |

## 边界护栏

- 不使用 headless / bypass 反爬
- 不修改 `infra/` 代码
- 分页采用 `infra/crawl/pagination_helpers.py`，helper 不覆盖时在 adapter 内写 fallback
- 不绕过 robots.txt