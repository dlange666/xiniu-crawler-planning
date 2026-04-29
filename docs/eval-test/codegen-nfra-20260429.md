# Codegen nfra Eval

> **类型**：`acceptance-report`
> **关联**：codegen wrapper / host `www.nfra.gov.cn`
> **验证 spec**：`codegen-output-contract.md` §3.1
> **作者**：generator (opencode) + wrapper verification
> **日期**：2026-04-29
> **判定**：`green`

## 1. 背景与目的

为 `www.nfra.gov.cn`（国家金融监督管理总局）生成采集适配器。站点主页面为
AngularJS，但可通过公开 JSON 数据完成 direct 采集：

- 列表：`GET https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild/data_itemId=861,pageIndex=1,pageSize=18.json`
- 详情：`GET https://www.nfra.gov.cn/cbircweb/DocInfo/SelectByDocId?docId=<docId>`

## 2. 复现命令

```bash
uv run pytest tests/gov_policy/test_nfra_adapter.py -q
uv run pytest tests/ -q
uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('gov_policy', 'www.nfra.gov.cn'))"
uv run python -m json.tool docs/task/active/task-codegen-nfra-2026-04-29.json
rm -f runtime/db/dev.db runtime/db/dev.db-wal runtime/db/dev.db-shm
uv run python scripts/run_crawl_task.py domains/gov_policy/nfra/nfra_seed.yaml --max-pages 30 --max-depth 1 --scope-mode same_origin --business-context gov_policy --task-id 7
uv run python scripts/audit_crawl_quality.py --task-id 7 --db runtime/db/dev.db --thresholds title_rate=0.95,body_100_rate=0.95,metadata_rate=0.30
```

## 3. Gate 结果

| Gate | Result |
|---|---|
| pytest_all | PASS (`125 passed`) |
| pytest_new | PASS (`8 passed`) |
| registry | PASS |
| workflow_docs | PASS |
| task_json | PASS |
| golden | PASS (`8 html`, `8 golden.json`) |
| live_smoke | PASS |
| audit | PASS |

## 4. Live smoke

```text
list_pages_fetched      = 3
detail_urls_discovered  = 54
detail_urls_fetched     = 27
raw_records_written     = 27
errors                  = 0
anti_bot_events         = 0
```

## 5. Audit stdout

```text
=== crawl_raw quality audit ===
records: 27
hosts:   1  ({'www.nfra.gov.cn': 27})

--- field hit rates ---
            title_rate: 100.0%
         body_100_rate: 100.0%
         body_300_rate: 100.0%
         body_500_rate: 100.0%
        body_1000_rate:  96.3%
         metadata_rate: 100.0%
      attachments_rate:   0.0%
        interpret_rate:  11.1%

--- body_len stats ---
  min=721  median=3065  mean=4969  max=29545

--- per-host cohort quality ---
  www.nfra.gov.cn: n=27  median_body=3065  low_quality=0

=== VERDICT: PASS ===
```

## 6. 文件清单

| 文件 | 路径 |
|---|---|
| Adapter | `domains/gov_policy/nfra/nfra_adapter.py` |
| Seed | `domains/gov_policy/nfra/nfra_seed.yaml` |
| Test | `tests/gov_policy/test_nfra_adapter.py` |
| Golden | `domains/gov_policy/nfra/nfra_golden_*` |
| Task | `docs/task/active/task-codegen-nfra-2026-04-29.json` |
| Plan | `docs/exec-plan/active/plan-20260429-codegen-nfra.md` |

## 7. PR handoff

- **建议标题**：`feature(nfra): add codegen adapter`
- **建议 base**：`main`
- **状态**：green，等待 review 后合并。

## 8. Notify message 草稿

```text
codegen nfra green
Host: www.nfra.gov.cn
Records: 27 raw records, errors=0, audit=PASS
Adapter: domains/gov_policy/nfra/nfra_adapter.py
```
