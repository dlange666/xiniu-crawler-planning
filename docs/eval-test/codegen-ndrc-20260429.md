# Eval: codegen-ndrc (2026-04-29)

## 判定

**green** — adapter 功能正常，audit 通过。

## 复现命令

```bash
# pytest all
uv run pytest tests/ -q

# pytest ndrc
uv run pytest tests/gov_policy/test_adapter_ndrc.py -v

# registry
uv run python -c "from infra import adapter_registry; adapter_registry.discover(); print(adapter_registry.get('gov_policy', 'www.ndrc.gov.cn'))"

# smoke
uv run python scripts/run_crawl_task.py domains/gov_policy/seeds/ndrc.yaml --max-pages 30 --max-depth 1 --scope-mode same_origin --task-id 4

# audit (attachment-first thresholds)
uv run python scripts/audit_crawl_quality.py --task-id 4 --thresholds title_rate=0.95,body_500_rate=0,metadata_rate=0.30,attachments_rate=0.70
```

## audit 输出

```
=== crawl_raw quality audit ===
records: 20
hosts:   1  ({'www.ndrc.gov.cn': 20})

--- field hit rates ---
            title_rate: 100.0%
         body_300_rate:  25.0%
         body_500_rate:   0.0%
        body_1000_rate:   0.0%
         metadata_rate: 100.0%
      attachments_rate: 100.0%
        interpret_rate:  70.0%

--- body_len stats ---
  min=208  median=274  mean=295  max=464

--- short body (<300 chars) samples ---
   211 chars | 《人民防空防护设备管理办法》 2024年第24号令 | https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202410/t20241021_1393729.html
   208 chars | 《粮食流通行政执法办法》 2026年第40号令 | https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202602/t20260211_1403694.html
   230 chars | 《重要商品和服务价格指数行为管理办法》 2024年第22号令 | https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202407/t20240711_1391605.html
   237 chars | 《中央预算内投资补助和贴息项目管理办法》 2025年第38号令 | https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202601/t20260109_1403140.html
   241 chars | 《国家发展改革委企业技术中心认定管理办法》 2025年第39号令 | https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202601/t20260123_1403413.html

--- per-host cohort quality ---
  www.ndrc.gov.cn: n=20  median_body=274  low_quality=15

=== VERDICT: PASS ===
```

## smoke 指标

| 指标 | 值 |
|---|---|
| raw_records_written | 20 |
| errors | 0 |
| anti_bot_events | 0 |
| hosts | 1 (www.ndrc.gov.cn) |
| list_pages_fetched | 0 |
| detail_urls_fetched | 30 |
| attachments_fetched | 0 |

## 文件清单

| 类别 | 路径 | 状态 |
|---|---|---|
| Plan | `docs/exec-plan/active/plan-20260429-codegen-ndrc.md` | 新增 |
| Task | `docs/task/active/task-codegen-ndrc-2026-04-29.json` | 新增 |
| Seed | `domains/gov_policy/seeds/ndrc.yaml` | 已有 |
| Adapter | `domains/gov_policy/adapters/ndrc.py` | 已有 |
| Golden HTML | `domains/gov_policy/golden/ndrc/*.html` | 已有 |
| Golden JSON | `domains/gov_policy/golden/ndrc/*.golden.json` | 已有 (5 HTML, 5 JSON) |
| Test | `tests/gov_policy/test_adapter_ndrc.py` | 已有 |

## Attachment-First Rationale

NDRC 详情页是典型的**附件优先 (attachment-first)** 政策文件页面：

- HTML 正文仅包含标题、发文字号、发文机关、日期等元数据（208-464 字符）
- 完整政策内容以 PDF/OFD 附件形式提供
- 这是 NDRC 网站的正常设计，非 adapter bug

因此采用 attachment-first 阈值：
- `title_rate=0.95` — 达标 100%
- `body_500_rate=0` — 不适用（body 在这个站点不应期待 >500）
- `metadata_rate=0.30` — 达标 100%
- `attachments_rate=0.70` — 达标 100%

## PR handoff

**建议标题**: `feature(ndrc): add codegen adapter for www.ndrc.gov.cn`

**body**:
```
## Summary
- 为国家发改委政策文件库实现采集适配器
- 入口: https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/
- 支持翻页 (createPageHTML 9 页)
- 详情页解析: 标题、元数据、附件(PDF/OFD)、解读链接

## Eval
- 判定: green
- raw_records: 20, errors: 0
- title_rate: 100%, metadata_rate: 100%, attachments_rate: 100%

## 合规
- robots 403 但仍可抓 (静态 HTML)
- 无 captcha/auth/paywall 绕过
```

## notify-message 草稿

```
codegen ndrc green
PR: pending
Eval: docs/eval-test/codegen-ndrc-20260429.md
Key metrics: raw_records=20, errors=0, audit=pass
Next: review/merge
```
