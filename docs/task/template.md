# 任务文件模板

用于 `docs/task/active/` 下的逐 PR 任务状态文件。

## 命名约定

- 文件路径：`docs/task/active/task-<pr-name>-<yyyy-mm-dd>.json`
- 完成后移至 `docs/task/completed/`，归档移至 `docs/task/archive/YYYY-Www/`

## 必备字段

`schema_version`、`file_kind`（取值 `pr-task-file`）、`description`、
`pr_name`、`branch`、`date`、`status_enum`、`tasks`。

## 任务记录字段

`id`、`title`、`status`、`plan_id`、`dependency`、`assignee`、
`last_updated`、`notes`。

## 示例

```json
{
  "schema_version": "1.0",
  "file_kind": "pr-task-file",
  "description": "MVP 阶段：跑通国务院文件库单源采集。",
  "pr_name": "mvp-statecouncil-crawl",
  "branch": "agent/feature-20260427-mvp-statecouncil-crawl",
  "date": "2026-04-27",
  "status_enum": ["pending", "in_progress", "verifying", "completed", "failed"],
  "tasks": [
    {
      "id": "T-20260427-101",
      "title": "[infra/http] 带 Retry-After 与抖动的基础 HTTP 客户端",
      "status": "pending",
      "plan_id": "PLAN-20260427-MVP-POLICY-CRAWLER",
      "dependency": [],
      "assignee": "generator",
      "last_updated": "2026-04-27T00:00:00Z",
      "notes": ""
    }
  ]
}
```
