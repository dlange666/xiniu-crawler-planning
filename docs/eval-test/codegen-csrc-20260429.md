# Eval: codegen-csrc (www.csrc.gov.cn)

> **判定**: green
> **日期**: 2026-04-29
> **任务 ID**: T-20260429-701

## 复现命令

```bash
uv run pytest tests/gov_policy/test_csrc_adapter.py -q
uv run pytest tests/ -q
uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('gov_policy', 'www.csrc.gov.cn'))"
uv run python -m json.tool docs/task/active/task-codegen-csrc-2026-04-29.json
rm -f runtime/db/dev.db runtime/db/dev.db-wal runtime/db/dev.db-shm
uv run python scripts/run_crawl_task.py domains/gov_policy/csrc/csrc_seed.yaml --max-pages 30 --max-depth 1 --scope-mode same_origin --business-context gov_policy --task-id 9
uv run python scripts/audit_crawl_quality.py --task-id 9 --db runtime/db/dev.db --thresholds title_rate=0.95,body_100_rate=0.95,metadata_rate=0.30
```

## audit 输出

```
=== crawl_raw quality audit ===
records: 25
hosts:   1  ({'www.csrc.gov.cn': 25})

--- field hit rates ---
            title_rate: 100.0%
         body_100_rate: 100.0%
         body_300_rate: 100.0%
         body_500_rate: 100.0%
        body_1000_rate: 100.0%
         metadata_rate: 100.0%
      attachments_rate:   0.0%
        interpret_rate:   0.0%

--- body_len stats ---
  min=1557  median=7556  mean=7807  max=13509

--- per-host cohort quality ---
  www.csrc.gov.cn: n=25  median_body=7556  low_quality=0

=== VERDICT: PASS ===
```

## 验收指标

| 检查 | 结果 |
|---|---|
| pytest | 122 passed (4 csrc + 118 others) |
| registry | gov_policy/www.csrc.gov.cn resolved |
| task JSON | valid |
| golden | 6 HTML + 6 JSON |
| live smoke | raw_records=25, errors=0 |
| audit | PASS (title=100%, body=100%, metadata=100%) |

## 文件清单

| 文件 | 状态 |
|---|---|
| `docs/exec-plan/active/plan-20260429-codegen-csrc.md` | created |
| `docs/task/active/task-codegen-csrc-2026-04-29.json` | updated |
| `domains/gov_policy/csrc/csrc_adapter.py` | created |
| `domains/gov_policy/csrc/csrc_seed.yaml` | created |
| `domains/gov_policy/csrc/__init__.py` | created |
| `domains/gov_policy/csrc/csrc_golden_*.html` (6) | created |
| `domains/gov_policy/csrc/csrc_golden_*.golden.json` (6) | created |
| `tests/gov_policy/test_csrc_adapter.py` | created |

## PR handoff

**建议标题**: `feature(csrc): add codegen adapter for www.csrc.gov.cn`

**Body**:
```markdown
## Summary
- 为 www.csrc.gov.cn (中国证券监督管理委员会) 实现采集适配器
- 入口: http://www.csrc.gov.cn/csrc/c106256/fg.shtml (规章列表)
- 采集 25 条政策文件详情

## Gates
- pytest: 122 passed
- registry: resolved
- live smoke: raw_records=25, errors=0
- audit: PASS (title=100%, body=100%, metadata=100%)

## Plan/Task/Eval
- Plan: docs/exec-plan/active/plan-20260429-codegen-csrc.md
- Task: docs/task/active/task-codegen-csrc-2026-04-29.json
- Eval: docs/eval-test/codegen-csrc-20260429.md
```

## notify-message 草稿

```
codegen csrc green
PR: pending
Eval: docs/eval-test/codegen-csrc-20260429.md
Key metrics: raw_records=25, errors=0, audit=pass
Next: review/merge
```

## 已知限制

- 分页: adapter 已支持 CSRC 单引号 `createPageHTML('page_div', total, cur, prefix, suffix, rows)`；本轮 smoke 在 `max_pages=30` 下抓取 5 个列表页、25 条详情，剩余详情受 max_pages 限制未抓完
- attachments: 详情页有 PDF/DOCX 下载链接，但默认不下载附件
- interpret_links: 当前无解读页链接

## Post-review Gate Rerun

> **时间**：2026-04-29T16:54:51+08:00
> **原因**：人工审查后补充 CSRC 单引号分页识别，并重跑完整 gates。

| Gate | Result |
|---|---|
| pytest_all | PASS (`122 passed`) |
| pytest_new | PASS (`4 passed`) |
| registry | PASS |
| task_json | PASS |
| golden | PASS (`6 HTML + 6 golden.json`) |
| live_smoke | PASS (`list_pages_fetched=5`, `detail_urls_discovered=80`, `detail_urls_fetched=25`, `raw_records_written=25`, `errors=0`) |
| audit | PASS (`title_rate=100%`, `body_100_rate=100%`, `metadata_rate=100%`) |

## 修订历史

| rev | 日期 | 摘要 |
|---|---|---|
| 1 | 2026-04-29 | 初始化 eval, green |

## Wrapper Gate Result

> **作者**：codegen wrapper
> **时间**：2026-04-29T16:53:08+08:00
> **最终判定**：`green`

| Gate | Result |
|---|---|
| pytest_all | PASS |
| pytest_new | PASS |
| registry | PASS |
| workflow_docs | PASS |
| task_json | PASS |
| golden | PASS |
| live_smoke | PASS |
| audit | PASS |

| 项 | 值 |
|---|---|
| host | `www.csrc.gov.cn` |
| branch | `agent/feature-20260429-codegen-csrc-t9` |
| opencode_exit_code | `0` |
| failed_gates | `none` |
| codegen_log | `runtime/codegen/csrc-1777452321.log` |
| worktree | `/Users/wangjisong/xiniu/code/xiniu-crawler-codegen-csrc-t9` |
