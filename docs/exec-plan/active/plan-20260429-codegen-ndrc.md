# Plan: codegen-ndrc

> **关联 spec**: `docs/prod-spec/codegen-output-contract.md`
> **状态**: active

## 目标

为 `www.ndrc.gov.cn` 实现采集适配器，采集国家发改委政策文件。

## 原子任务

| ID | 任务 | 验收 |
|---|---|---|
| T-20260429-101 | 站点探查 (probe_source.py) | runtime/probe/ndrc/ 有 verdict |
| T-20260429-102 | 实现 adapter (ndrc.py) | 满足 ADAPTER_META 校验 |
| T-20260429-103 | 实现 seed (ndrc.yaml) | 含 scope_mode: same_origin |
| T-20260429-104 | 采集 golden 样本 (>=5 组) | HTML + .golden.json |
| T-20260429-105 | 编写测试 (test_adapter_ndrc.py) | 覆盖 registry/parse_list/parse_detail |
| T-20260429-106 | 跑 gates (pytest + live smoke + audit) | audit 退出码 0 |
| T-20260429-107 | 写 eval 并判定 | green/red/partial |
| T-20260429-108 | PR handoff | 建议标题和 body |

## 边界护栏

- 不 headless (只用 direct/SSR)
- 不绕过反爬 (robots/captcha/auth/paywall)
- 不改 infra / AGENTS.md / pyproject.toml
- 不 import 其它业务域