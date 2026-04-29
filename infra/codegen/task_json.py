"""Task JSON 校验与规范化（兜底 agent 输出 markdown fence / 散文包裹）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NamedTuple


class JsonValidationResult(NamedTuple):
    ok: bool
    repaired: bool
    error: str | None = None


def _extract_json_objects(text: str) -> list[str]:
    """从文本中拆出平衡的 JSON-like 对象，识别字符串避免误切。"""
    objects: list[str] = []
    starts = [match.start() for match in re.finditer(r"\{", text)]
    for start in starts:
        depth = 0
        in_string = False
        escaped = False
        for idx, char in enumerate(text[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    objects.append(text[start:idx + 1])
                    break
    return objects


def _validate_pr_task_file(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"]

    required = {
        "schema_version", "file_kind", "description", "pr_name",
        "branch", "date", "status_enum", "tasks",
    }
    for key in sorted(required - set(data)):
        errors.append(f"missing top-level key: {key}")

    if data.get("file_kind") != "pr-task-file":
        errors.append("file_kind must be pr-task-file")
    if not isinstance(data.get("status_enum"), list):
        errors.append("status_enum must be a list")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty list")
        return errors

    task_required = {
        "id", "title", "status", "plan_id",
        "dependency", "assignee", "last_updated", "notes",
    }
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        for key in sorted(task_required - set(task)):
            errors.append(f"tasks[{index}] missing key: {key}")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not re.fullmatch(r"T-\d{8}-\d{3}", task_id):
            errors.append(f"tasks[{index}].id must match T-YYYYMMDD-NNN")
        if task.get("status") not in data.get("status_enum", []):
            errors.append(f"tasks[{index}].status is not in status_enum")
        if not isinstance(task.get("dependency", []), list):
            errors.append(f"tasks[{index}].dependency must be a list")
    return errors


def normalize_task_json(path: Path) -> JsonValidationResult:
    """校验 task JSON 并规范化常见 agent 非标输出。

    修复策略刻意收窄：只从 markdown fence / 散文包裹中提取一个平衡 JSON 对象，
    不猜缺逗号、不删注释——避免静默改变语义。
    """
    if not path.exists():
        return JsonValidationResult(False, False, "task JSON missing")

    raw = path.read_text(encoding="utf-8")
    candidates = [(raw, False)]
    for extracted in _extract_json_objects(raw):
        if extracted == raw.strip():
            continue
        candidates.append((extracted, True))

    last_error: str | None = None
    for candidate, repaired in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = f"JSONDecodeError: {exc.msg} at line {exc.lineno} column {exc.colno}"
            continue
        schema_errors = _validate_pr_task_file(data)
        if schema_errors:
            return JsonValidationResult(False, repaired, "; ".join(schema_errors))
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return JsonValidationResult(True, repaired, None)

    return JsonValidationResult(False, False, last_error or "no JSON object found")
