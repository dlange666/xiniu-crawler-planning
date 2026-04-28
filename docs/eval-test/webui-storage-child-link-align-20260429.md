# WebUI 入库信息子链接 label 对齐验收

> **类型**：`ui-eval`
> **关联**：`plan-20260428-webui-bootstrap` / `T-20260429-102`
> **验证 spec**：`webui.md` rev 12 §7, §12
> **日期**：2026-04-29
> **判定**：`green`

## 1. 目标

针对采集详情页入库信息区修复子链接展示：

- “解读 / 附件 / 链接”不再嵌在 `Attachments` 的 value 内部。
- 子链接 label 与“源 URL / Raw blob / Created at / Attachments”共用同一 label 栅格。
- 子链接右侧标题与 URL 与上方 value 内容左边缘对齐。
- Playwright 临时脚本和截图只保存在 `/tmp`，不加入 git。

## 2. 验证命令

```bash
cd webui/frontend && npm run build
uv run pytest tests/webui -q
uv run ruff check webui tests/webui
```

## 3. 浏览器验证

待本地服务启动后，用 Playwright/Chrome 访问：

| 视口 | URL | 预期 |
|---|---|---|
| Desktop 1440x960 | `/ui/tasks/2026042841/items/14` | “源 URL / Raw blob / Created at / Attachments / 解读”的 label 列均为 `left=999/right=1103`；value 左边缘均为 `1115` |
| Mobile 390x844 | `/ui/tasks/2026042841/items/14` | 入库信息行堆叠后 label/value 左边缘均为 `42`，无逐字断裂或错位 |

截图保存在 `/tmp/xiniu-webui-storage-align/`，不加入 git。

## 4. 结论

- **判定**：`green`
- **风险**：Vite 仍提示 Ant Design Pro bundle 大于 500 kB；这是既有构建体积问题，本次未扩大依赖。

## 修订历史

| 修订 | 日期 | 摘要 |
|---|---|---|
| rev 1 | 2026-04-29 | 初版 —— 入库信息子链接 label 对齐验收 |
