# MOST codegen 采集任务验收报告

> **类型**：`codegen-eval`
> **关联**：`plan-20260428-codegen-most` / `T-20260428-501`..`T-20260428-509`
> **验证 spec**：`codegen-output-contract.md §3.1` + `docs/codegen-pipeline.md §4.5`
> **日期**：2026-04-28
> **判定**：`green`

## 1. 背景与目的

使用 `docs/codegen-pipeline.md` 为科技部 `www.most.gov.cn` 完成一个
`gov_policy` 单 host 采集 adapter，并用 live smoke + audit 防止只通过结构测试的假 green。

## 2. 复现命令

```bash
uv run pytest tests/ -q

uv run pytest tests/gov_policy/test_adapter_most.py -v

uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('gov_policy', 'www.most.gov.cn'))"

STORAGE_PROFILE=dev \
CRAWLER_DB_PATH=/Users/wangjisong/xiniuCode/xiniu-crawler-codegen-most/runtime/db/dev.db \
CRAWLER_BLOB_ROOT=/Users/wangjisong/xiniuCode/xiniu-crawler-codegen-most/runtime/raw \
uv run python scripts/run_crawl_task.py \
  domains/gov_policy/seeds/most.yaml \
  --max-pages 30 --max-depth 1 --scope-mode same_origin --task-id 2026042841

STORAGE_PROFILE=dev \
CRAWLER_DB_PATH=/Users/wangjisong/xiniuCode/xiniu-crawler-codegen-most/runtime/db/dev.db \
CRAWLER_BLOB_ROOT=/Users/wangjisong/xiniuCode/xiniu-crawler-codegen-most/runtime/raw \
uv run python scripts/audit_crawl_quality.py \
  --task-id 2026042841 \
  --thresholds title_rate=0.95,body_500_rate=0.70,metadata_rate=0.30
```

## 3. Smoke 指标

| 指标 | 值 |
|---|---:|
| list_pages_fetched | 1 |
| detail_urls_discovered | 14 |
| detail_urls_fetched | 14 |
| interpret_pages_fetched | 0 |
| attachments_fetched | 0 |
| raw_records_written | 14 |
| raw_records_dedup_hit | 0 |
| rejected_by_scope | 0 |
| rejected_by_robots | 0 |
| errors | 0 |
| anti_bot_events | 0 |

`robots.txt` 返回 404，未声明拒绝；本次未触发 challenge / captcha / auth / paywall 信号。

## 4. Audit stdout

```text
=== crawl_raw quality audit ===
records: 14
hosts:   1  ({'www.most.gov.cn': 14})

--- field hit rates ---
            title_rate: 100.0%
         body_300_rate:  92.9%
         body_500_rate:  85.7%
        body_1000_rate:  85.7%
         metadata_rate: 100.0%
      attachments_rate:  14.3%
        interpret_rate:  50.0%

--- body_len stats ---
  min=235  median=4870  mean=5461  max=16260

--- short body (<300 chars) samples ---
   235 chars | 科技部办公厅关于印发《“创新积分制”工作指引（全国试行版）》的通知 | https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/gfxwj/gfxwj2024

--- per-host cohort quality ---
  www.most.gov.cn: n=14  median_body=4870  low_quality=1

=== VERDICT: PASS ===
```

## 5. 文件清单

| 类型 | 路径 |
|---|---|
| Plan | `docs/exec-plan/active/plan-20260428-codegen-most.md` |
| Task | `docs/task/active/task-codegen-most-2026-04-28.json` |
| Eval | `docs/eval-test/codegen-most-20260428.md` |
| Adapter | `domains/gov_policy/adapters/most.py` |
| Seed | `domains/gov_policy/seeds/most.yaml` |
| Golden | `domains/gov_policy/golden/most/` |
| Tests | `tests/gov_policy/test_adapter_most.py` |

## 6. 结论

- **判定**：`green`
- **依据**：MOST 专项测试 10/10 通过；live smoke 抓到 14 条真实详情且 0 error；
  audit 退出码 0，核心阈值全部通过。
- **合规**：未启用 headless；未绕过验证码、登录、付费墙、技术 challenge 或 robots 明示拒绝。
- **已知限制**：列表页只采主政策 `flfg/bmgz/gfxwj`，`zcjd` 作为解读链接在详情页内发现，不作为主详情列表抓取。

## 7. PR handoff

Draft PR: https://github.com/dlange666/xiniu-crawler-planning/pull/4

建议 PR 标题：

```text
feature(most): add codegen adapter
```

建议 PR body：

```markdown
## Summary
- add MOST (`www.most.gov.cn`) gov_policy adapter, seed, golden fixtures, and tests
- record codegen workflow artifacts for T-20260428-501..T-20260428-509
- validate live smoke and audit for task_id=2026042841

## Verification
- `uv run pytest tests/ -q`
- `uv run pytest tests/gov_policy/test_adapter_most.py -v`
- `uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('gov_policy', 'www.most.gov.cn'))"`
- `uv run python scripts/run_crawl_task.py domains/gov_policy/seeds/most.yaml --max-pages 30 --max-depth 1 --scope-mode same_origin --task-id 2026042841`
- `uv run python scripts/audit_crawl_quality.py --task-id 2026042841 --thresholds title_rate=0.95,body_500_rate=0.70,metadata_rate=0.30`

## Results
- raw_records_written=14
- errors=0
- anti_bot_events=0
- audit=PASS
```

## 8. notify-message 草稿

```text
codegen most green
PR: https://github.com/dlange666/xiniu-crawler-planning/pull/4
Eval: docs/eval-test/codegen-most-20260428.md
Key metrics: raw_records=14, errors=0, audit=pass
Next: review draft PR, then merge after owner approval
```

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-28 | 初版 —— MOST codegen adapter live smoke + audit green |
