# WebUI 列表展示与对齐优化验收

> **类型**：`ui-eval`
> **关联**：`plan-20260428-webui-bootstrap` / `T-20260429-101`
> **验证 spec**：`webui.md` rev 12 §2, §7, §12
> **日期**：2026-04-29
> **PR**：https://github.com/dlange666/xiniu-crawler-planning/pull/5
> **判定**：`green`

## 1. 目标

针对本地 MOST smoke 数据优化 React WebUI 的可读性：

- 任务列表首列不再与 Source/Host 重叠。
- URL 列表把标题、URL、URL 指纹分层展示，减少长 URL 对列宽的挤压。
- Source 参数、入库信息、Source metadata 使用固定 label 网格，提升左右对齐。
- 移动端将双栏信息区堆叠，避免窄列逐字换行。

## 2. 验证命令

```bash
cd webui/frontend && npm run build
uv run pytest tests/webui -q
uv run ruff check webui tests/webui
```

## 3. 浏览器验证

本地服务：

```bash
STORAGE_PROFILE=dev \
CRAWLER_DB_PATH=/Users/wangjisong/xiniuCode/xiniu-crawler-codegen-most/runtime/db/dev.db \
CRAWLER_BLOB_ROOT=/Users/wangjisong/xiniuCode/xiniu-crawler-codegen-most/runtime/raw \
WEBUI_PORT=8766 \
uv run python scripts/run_webui.py
```

Playwright 访问路径：

| 视口 | URL | 结果 |
|---|---|---|
| Desktop 1440x960 | `/ui` | 任务 ID、Source、Volume 不重叠 |
| Desktop 1440x960 | `/ui/tasks/2026042841` | URL 列表按标题/URL/fp 分层；State/Fetch/Action 对齐 |
| Desktop 1440x960 | `/ui/tasks/2026042841/items/14` | 入库信息与 metadata label 对齐 |
| Mobile 390x844 | `/ui/tasks/2026042841` | Source 参数与 Depth 分布堆叠；URL 表不挤压信息区 |
| Mobile 390x844 | `/ui/tasks/2026042841/items/14` | 入库信息堆叠，长 URL 不逐字断裂 |

截图保存在 `/tmp/xiniu-webui-polish/`，属于本地临时产物，不加入 git。

## 4. 结论

- **判定**：`green`
- **风险**：Vite 仍提示 Ant Design Pro bundle 大于 500 kB；这是既有构建体积问题，本次未扩大依赖。

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版 —— WebUI 列表展示与对齐优化验收 |
