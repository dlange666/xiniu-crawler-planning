# Plan: codegen-nfra

> **关联 spec**: `docs/prod-spec/codegen-output-contract.md`

## 目标

为 `www.nfra.gov.cn`（国家金融监督管理总局）生成采集适配器。

| 项 | 值 |
|---|---|
| business_context | `gov_policy` |
| host | `www.nfra.gov.cn` |
| entry URL | `https://www.nfra.gov.cn/cn/view/pages/zhengwuxinxi/zhengfuxinxi.html` |
| scope_mode | `same_origin` |
| render_mode | `direct`（GET 静态 JSON + 详情 JSON API，无需 headless） |

## 站点探查结论

- **verdict**: `json_api`
- **render_required**: `false`
- **anti_bot_detected**: `false`
- **结论**: 使用 NFRA 静态 JSON 缓存作为列表入口，详情走 `/cbircweb/DocInfo/SelectByDocId`；当前 direct runner 可采集。

## 原子任务

| ID | 任务 | 验收门 |
|---|---|---|
| T-20260429-701 | 站点探查 & 页面结构分析 | probe-result.json 已生成，verdict=static_html |
| T-20260429-702 | 写 adapter、seed、golden | adapter 通过 meta 校验，seed 含 scope_mode |
| T-20260429-703 | 写测试 | test_nfra_adapter.py 全绿 |
| T-20260429-704 | 跑 gates（pytest + registry + live smoke + audit） | audit 退出码 0 |
| T-20260429-705 | 写 eval + PR handoff | green 判定 + notify-message 草稿 |

## 边界护栏

- **不 headless**: 使用 direct JSON 模式
- **不绕过反爬**: 无 challenge/captcha/auth/paywall
- **不改 infra**: 只在 domains/gov_policy/nfra/ 下工作
- **scope_mode**: same_origin（跨子域需人审）

## 执行顺序

1. 读取 `runtime/probe/nfra/redirected.html` 与站点 JS，定位 JSON 数据入口
2. 实现 `nfra_adapter.py`（parse_list + parse_detail）
3. 实现 `nfra_seed.yaml`
4. 抓取 golden 样本（5+ 列表页 + 1+ 详情页）
5. 写 `test_nfra_adapter.py`
6. 跑 gates（第 4.5 节所有命令）
7. 写 eval 并判定 green/red
