"""生成 task JSON 骨架、per-task prompt 和 red feedback prompt。"""

from __future__ import annotations

import argparse
import json
import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Any

from infra.codegen.paths import (
    context_spec_name,
    slug,
    task_artifact_path,
)
from infra.codegen.shell import clip


def write_task_skeleton(worktree: Path, args: argparse.Namespace, branch: str) -> Path:
    """预置规范的 task JSON。Agent 改字段值即可，不必从零拼结构。

    最常见失败模式是 markdown / 散文包裹一个像 JSON 的对象——预置骨架直接消除。
    """
    today = date.today()
    host_slug = slug(args.host)
    task_path = task_artifact_path(worktree, args)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    plan_id = f"plan-{today:%Y%m%d}-codegen-{host_slug}"
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "file_kind": "pr-task-file",
        "description": f"codegen-{host_slug}: 为 {args.host} 生成采集适配器。",
        "pr_name": f"codegen-{host_slug}",
        "branch": branch,
        "date": today.isoformat(),
        "status_enum": ["pending", "in_progress", "verifying", "completed", "failed"],
        "tasks": [
            {
                "id": f"T-{today:%Y%m%d}-701",
                "title": f"[codegen/{host_slug}] 生成并验收采集适配器",
                "status": "in_progress",
                "plan_id": plan_id,
                "spec_ref": "codegen-output-contract.md §3.1；docs/codegen-pipeline.md §4",
                "dependency": [],
                "assignee": "generator",
                "last_updated": now,
                "notes": (
                    "wrapper 预生成 JSON 骨架；agent 更新时必须保持标准 JSON，"
                    "wrapper gates 会校验并在常见包裹文本场景下自动规范化。"
                ),
            }
        ],
    }
    task_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return task_path


def write_per_task_prompt(worktree: Path, args: argparse.Namespace) -> Path:
    """生成本次的 .codegen-prompt.md（pipeline 之外的目标特化部分）。"""
    host_slug = slug(args.host)
    spec_name = context_spec_name(args.business_context)
    today = date.today()
    task_id = getattr(args, "codegen_task_id", None)
    data_kind = getattr(args, "data_kind", "policy")
    scope_description = getattr(args, "scope_description", None)
    task_line = f"| crawl_task.task_id | `{task_id}` |\n" if task_id is not None else ""
    scope_line = (
        f"| scope_description | `{scope_description}` |\n"
        if scope_description else ""
    )
    prompt = textwrap.dedent(f"""\
        # 任务：为 {args.host} 实现采集适配器

        > **前置阅读**：你已加载 `docs/codegen-pipeline.md`。**严格按它执行**——
        > git-worktree / plan / task / gates / eval / PR handoff / notify-message
        > 的顺序和允许写入范围都在 pipeline 里。

        ## 目标

        | 项 | 值 |
        |---|---|
        | business_context | `{args.business_context}` |
        | data_kind | `{data_kind}` |
        | host | `{args.host}` |
        | entry URL | `{args.entry_url}` |
        | scope_mode | `{args.scope_mode}` |
        {task_line}{scope_line}\
        | render_mode | `direct`（确认是 SSR 后再写；JS 渲染站本期不接） |

        ## 必须交付

        按 pipeline §4-§6 工作流：

        1. 写 plan：`docs/exec-plan/active/plan-{today:%Y%m%d}-codegen-{host_slug}.md`
        2. 更新 task：wrapper 已预先生成合法 JSON 骨架
           `docs/task/active/task-codegen-{host_slug}-{today}.json`。只允许编辑 JSON
           字段值，不要输出 markdown fence、注释、尾逗号或任何 JSON 外文本；
           每次编辑后必须执行 `uv run python -m json.tool <task-json>`。
        3. 实现：
           - `domains/{args.business_context}/{host_slug}/{host_slug}_adapter.py`
           - `domains/{args.business_context}/{host_slug}/{host_slug}_seed.yaml`
             （**必须**含 `scope_mode: {args.scope_mode}`）
           - `domains/{args.business_context}/{host_slug}/{host_slug}_golden_*.html`
           - `domains/{args.business_context}/{host_slug}/{host_slug}_golden_*.golden.json`
           - `tests/{args.business_context}/test_{host_slug}_adapter.py`
        4. 跑 pipeline §5 的验收门，**包括 live smoke + audit 脚本**
        5. 写 eval：`docs/eval-test/codegen-{host_slug}-{today:%Y%m%d}.md`，判定来自 audit 退出码
        6. eval 最后一节写 PR handoff 与 notify-message 草稿

        ## 强制收口协议

        每次实现或修复后，按顺序执行：

        ```bash
        uv run pytest tests/{args.business_context}/test_{host_slug}_adapter.py -q
        uv run pytest tests/ -q
        uv run python -c "from infra import adapter_registry; adapter_registry.discover(); \
print(adapter_registry.get('{args.business_context}', '{args.host}'))"
        uv run python -m json.tool docs/task/active/task-codegen-{host_slug}-{today}.json
        ls domains/{args.business_context}/{host_slug}/{host_slug}_golden_*.html \
           domains/{args.business_context}/{host_slug}/{host_slug}_golden_*.golden.json
        rm -f runtime/db/dev.db runtime/db/dev.db-wal runtime/db/dev.db-shm
        uv run python scripts/run_crawl_task.py \
domains/{args.business_context}/{host_slug}/{host_slug}_seed.yaml \
--max-pages 30 --max-depth 1 --scope-mode {args.scope_mode} \
--business-context {args.business_context} --task-id {args.smoke_task_id}
        uv run python scripts/audit_crawl_quality.py \
--task-id {args.smoke_task_id} --db runtime/db/dev.db \
--thresholds title_rate=0.95,body_100_rate=0.95,metadata_rate=0.30
        ```

        最终判定只能来自上述 gates：

        - 全部 PASS：eval 写 `green`，task 状态写 `verifying`（PR 创建前不要写 `completed`）
        - 任一 FAIL：eval 写 `red` 或 `partial`，task 状态写 `failed`

        禁止只凭单测 / registry 通过写 green；禁止在 live smoke / audit 未跑时写 green。
        禁止把旧 `runtime/db/dev.db` checkpoint 造成的 0 records 当作源站失败。
        禁止把可通过静态 JSON / CDN / API / feed / SSR 采集的 JS shell 直接写成
        `render_required`。

        ## 解析质量硬规则

        - `ParseDetailResult.source_metadata` 必须是 `SourceMetadata(raw={{...}})`；
          测试读取用 `result.source_metadata.raw`，不得当作普通 dict。
        - `body_text` 不得包含 `var `、`function`、`document.`、`window.`、
          `<script`、`</script`、`$(...)` 等脚本噪声；正文若来自 JS 模板字面量，
          只能抽取正文变量自身，不能从第一个反引号截到最后一个反引号。
        - `detail_links` 必须属于本任务业务 scope。audit 出现 short body 或低质量
          URL 时，先判断该 URL 是否是导航 / 搜索 / 社媒 / 移动入口 / 站点说明 /
          栏目页等非政策详情；非业务详情必须在 `parse_list` 或
          `ADAPTER_META.detail_url_pattern` 中过滤，不得通过降低 gate 通过。
        - `next_pages` 按自然页码排序，不能出现 `1, 10, 11, 2` 这类字典序。

        ## Golden 覆盖硬规则

        必须使用一一配对命名：

        - `{host_slug}_golden_list_1.html` + `{host_slug}_golden_list_1.golden.json`
        - `{host_slug}_golden_detail_1.html` + `{host_slug}_golden_detail_1.golden.json`
          （至少 3 个 detail）
        - 有分页信号时再加 `{host_slug}_golden_list_2.html` +
          `{host_slug}_golden_list_2.golden.json`

        每个 `.golden.json` 必须由当前 adapter 输出重新生成并通过
        `uv run python -m json.tool`。聚合型 JSON 不能替代同名配对样本。

        ## red 前必须排查

        live smoke / audit 失败时不能立即结束。必须先做并在 eval 记录：

        1. 删 `runtime/db/dev.db*` 重跑 live smoke
        2. curl seed URL，确认 HTTP 状态、content-type、响应体
        3. 单独 `parse_list(seed_response, seed_url)`，确认 `detail_links > 0`
        4. curl 一个 detail URL，确认 `parse_detail` 抽出 title / body / metadata
        5. 逐条分析 audit short body / script_noise / detail_url_pattern miss，
           判断是正文抽取污染还是非业务链接误入
        6. parser 可用但 runner 无数据时，检查 seed URL / scope / robots /
           runtime checkpoint / `ADAPTER_META.list_url_pattern`
        7. 上述全部完成后才允许写 red

        ## 你需要自己探的事

        - 翻页：实际 fetch 一次列表页，看是否有 `index_N.htm` / `?page=N` /
          "下一页"按钮 / `createPageHTML` / `data-page` / 公开 JS page config，
          按 pipeline §3 先用 `infra/crawl/pagination_helpers.py` helper
        - infra helper 返回空但 HTML/JS 有明确稳定可静态解析的分页 / API / 字段信号时，
          不能直接放弃或写 red。在 `{host_slug}_adapter.py` 内实现 host-bounded
          fallback（纯函数、不联网、不改 infra），用 golden / test 覆盖；eval 记录
          helper 未覆盖、fallback 规则、是否建议另开 infra 任务提升。
          **本 codegen 任务禁止修改 `infra/`。**
        - 有分页信号时，`tests/{args.business_context}/test_{host_slug}_adapter.py`
          必须断言 `parse_list(...).next_pages` 至少含 1 个预期分页 URL；golden JSON
          也要记录对应 `next_pages`
        - 详情 URL 模式：从列表 HTML 抽 5+ 链接归纳 detail_url_pattern 正则
        - 跨子域：详情链接散布到 `*.{args.host.replace("www.", "")}` 子站时，
          seed 必须设 `scope_mode: same_etld_plus_one`，CLI 也要显式同步（已知陷阱）
        - 详情字段：参考 `docs/prod-spec/{spec_name}` 字段表
          （title / body / 发文字号 / 发文机关 / 成文日期 / 发布日期 /
          attachments / interpret_links）

        ## 给我的最终回报

        eval 写完后告诉我：

        1. audit 输出（粘贴 audit_crawl_quality.py 的 stdout）
        2. 验收判定（green / red / partial）+ 失败的 gate
        3. 子域分布与 cohort 质量（audit 已输出，简述）
        4. 已知 todo（哪些字段 / cohort 没覆盖到）
    """)
    f = worktree / ".codegen-prompt.md"
    f.write_text(prompt)
    return f


def write_feedback_prompt(
    worktree: Path,
    args: argparse.Namespace,
    gate_run: GateRunResult,  # noqa: F821 — 循环导入避险，运行期不解引用
    attempt: int,
) -> Path:
    failed = [name for name, ok in gate_run.results.items() if not ok]
    sections: list[str] = []
    for gate in failed:
        output = gate_run.details.get(gate, "")
        sections.append(f"### {gate}\n\n```text\n{clip(output, 6000)}\n```")
    if not sections:
        sections.append(
            "No failed gate details were captured; rerun full gates and inspect output."
        )
    failed_output = "\n\n".join(sections)
    path = worktree / ".codegen-feedback.md"
    path.write_text(
        textwrap.dedent(f"""\
        # Wrapper red feedback attempt {attempt}

        Wrapper gates 是最终判定。所有 gate 通过前不准写 green。
        在当前 worktree 原地修复，不要重启任务、不要降阈值、不要改 `infra/`。

        Failed gates: {", ".join(failed) if failed else "none"}

        Required triage:

        1. 修代码前先看下方失败 gate 输出。
        2. audit short body 时判断 URL 是否在业务 scope 外；非业务链接（导航 /
           搜索 / 社媒 / 移动入口）在 `parse_list` 过滤或收紧
           `ADAPTER_META.detail_url_pattern`。
        3. audit script noise 时修 `parse_detail`，让 `body_text` 排除 JS / CSS /
           导航文本；不要靠污染文本去凑长度。
        4. pytest 在 metadata 上挂时记得 `source_metadata` 是
           `SourceMetadata(raw={{...}})`，测试读 `.raw`。
        5. parser 改完后基于当前 adapter 重新生成成对 golden JSON；HTML/JSON 必须一一对应。
        6. 全部修完后重跑 `.codegen-prompt.md` 的完整收口 gates。

        ## Failed Gate Output

        {failed_output}
        """),
        encoding="utf-8",
    )
    return path
