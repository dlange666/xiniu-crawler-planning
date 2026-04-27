# 架构

本文件只描述**仓库级 high-level 架构**：分层、目录结构、依赖规则、几条
关键决策。具体业务域的子模块拆分、字段、流水线编排写在对应
`docs/prod-spec/<domain>-<vN>.md`。详细论证见
`docs/research/research-ai-first-crawler-system-20260427.md`。

## 1. 分层

```
Control Plane:  Task API · Policy/Scope · Frontier · Lease
Data Plane:     Fetcher → (Renderer 按需) → Parser → AI Extractor → Dedup → Sink
```

- 控制面自研，数据面复用成熟组件。
- AI 不进入请求主路径，仅出现在高不确定决策点（页面分类、字段抽取、URL 排序、反爬识别）。

## 2. 目录结构

- `domains/<context>/`：业务域（bounded context），承载业务规则与领域语言。新增前必须先有 `docs/prod-spec/<context>-<vN>.md`。
- `infra/`：跨域技术能力。**不含**业务规则。判定标准——能被另一个业务域原样复用的才放这里。

## 3. 依赖规则

```
domains/<X>/*  →  infra/*          ✓
domains/<A>/*  →  domains/<B>/*    ✗（业务域之间禁止直接依赖）
infra/*        →  domains/*        ✗（反向禁止）
```

业务域内部子模块的依赖关系由该域 spec 显式声明。后续加 import-linter 守护。

## 4. 关键决策

- **抓取层级顺序**：`feed/sitemap → static → 接口拦截 → SSR/DOM → headless 渲染`，按信号递进。
- **去重位置**：source 层不去重；解析层用联合键严格去重；simhash 仅作信号。
- **存储抽象**：`infra/storage/` 通过 `STORAGE_PROFILE=dev|prod` 切换；dev=SQLite+本地 FS，prod=PolarDB+阿里云 OSS。
- **反爬合规**：robots 入口前置；命中 challenge/captcha/WAF/auth → cooldown + 人工，**不重试不绕过**。
- **可观测性**：结构化日志先行，OTel/Grafana 推迟到 M5（TD-005）。

## 5. 与研究报告的偏离

- 不引入 etcd/Kafka：MVP 单进程 + SQLite；扩到多 worker 时再评估 Redis/RabbitMQ。
- 不接入邮件、PDF→文本、simhash 自动合并、多租户、删除链路（详见 `docs/exec-plan/tech-debt-tracker.md`）。
