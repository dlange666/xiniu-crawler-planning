#!/usr/bin/env python3
"""一键 codegen：传 host + entry URL，自动产出 adapter + plan + task + eval。

把"手动 worktree → 手写 prompt → 调 opencode → 跑测试 → 跑 audit → 写 eval"
这套流程封装成单脚本。模型由 --model 参数指定，可换 minimax / sonnet / 其它。

用法：
    uv run python scripts/run_codegen_for_adapter.py \\
        --host www.most.gov.cn \\
        --entry-url https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/ \\
        --scope-mode same_origin \\
        --model opencode/minimax-m2.5-free

退出码：0=audit pass，1=任意 gate fail。
失败时 worktree 不会被删，方便人工查证；成功后由人决定合回主分支。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIEF = REPO / "docs/codegen-brief.md"


def slug(host: str) -> str:
    """www.most.gov.cn → most"""
    return host.replace("www.", "").split(".")[0].replace("-", "_")


def sh(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> int:
    """执行命令，stdout/stderr 直通终端。"""
    print(f"\n$ {' '.join(cmd)}")
    rc = subprocess.run(cmd, cwd=cwd).returncode
    if check and rc != 0:
        sys.exit(rc)
    return rc


def sh_ok(cmd: list[str], *, cwd: Path | None = None) -> bool:
    return sh(cmd, cwd=cwd, check=False) == 0


def write_per_task_prompt(worktree: Path, args: argparse.Namespace) -> Path:
    """生成本次的 .codegen-prompt.md，brief 之外的目标特化部分。"""
    prompt = textwrap.dedent(f"""\
        # 任务：为 {args.host} 实现采集适配器

        > **前置阅读**：你已加载 `docs/codegen-brief.md`。**严格按它执行**——
        > 目录禁区、infra 能力索引、Plan/Task/Eval 三件套、验收门、失败回报模板都在 brief 里。

        ## 目标

        | 项 | 值 |
        |---|---|
        | business_context | `{args.business_context}` |
        | host | `{args.host}` |
        | entry URL | `{args.entry_url}` |
        | scope_mode | `{args.scope_mode}` |
        | render_mode | `direct`（确认是 SSR 后再写；JS 渲染站本期不接） |

        ## 必须交付

        按 brief §3 工作流：

        1. 写 plan：`docs/exec-plan/active/plan-{date.today():%Y%m%d}-codegen-{slug(args.host)}.md`
        2. 写 task：`docs/task/active/task-codegen-{slug(args.host)}-{date.today()}.json`
        3. 实现：
           - `domains/{args.business_context}/adapters/{slug(args.host)}.py`
           - `domains/{args.business_context}/seeds/{slug(args.host)}.yaml`（**必须**含 `scope_mode: {args.scope_mode}`）
           - `tests/{args.business_context}/test_adapter_{slug(args.host)}.py`（结构性测试，不依赖 golden）
        4. 跑 brief §4 的 5 道验收门，**包括 audit 脚本**
        5. 写 eval：`docs/eval-test/codegen-{slug(args.host)}-{date.today():%Y%m%d}.md`，判定来自 audit 退出码

        ## 你需要自己探的事

        - 翻页：实际 fetch 一次列表页，看是否有 `index_N.htm` / `?page=N` / "下一页"按钮，按 brief §2.2 选 helper
        - 详情 URL 模式：从列表 HTML 里抽 5+ 链接，归纳 detail_url_pattern 正则
        - 跨子域：如详情链接散布到 `*.{args.host.replace("www.", "")}` 的子站，
          seed 必须设 `scope_mode: same_etld_plus_one`，且 CLI 也要显式同步（已知陷阱）
        - 详情字段：参考 `docs/prod-spec/domain-{args.business_context}.md` 的字段表
          （title / body / 发文字号 / 发文机关 / 成文日期 / 发布日期 / attachments / interpret_links）

        ## 给我的最终回报

        eval 写完后告诉我：

        1. audit 输出（粘贴 audit_crawl_quality.py 的 stdout）
        2. 验收判定（green / red / partial）+ 失败的 gate（如 red）
        3. 子域分布与 cohort 质量（audit 已输出，简述）
        4. 已知 todo（哪些字段 / cohort 没覆盖到）
    """)
    f = worktree / ".codegen-prompt.md"
    f.write_text(prompt)
    return f


def setup_worktree(worktree: Path, branch: str, force: bool) -> None:
    """幂等创建 worktree。--force 触发硬重置：rm -rf + prune + 删分支。

    硬重置必要性：opencode 偶尔异常退出会留下 worktree 半完成状态，
    `git worktree remove --force` 不一定能清理干净。
    """
    if worktree.exists() or branch_exists(branch):
        if not force:
            sys.exit(f"worktree/branch 已存在：{worktree} / {branch}（加 --force 硬重置）")
        print(f"硬清理 worktree + branch：{worktree} / {branch}")
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
        sh(["git", "worktree", "prune"], check=False)
        if branch_exists(branch):
            sh(["git", "branch", "-D", branch], check=False)
    sh(["git", "worktree", "add", "-b", branch, str(worktree), "HEAD"])


def branch_exists(branch: str) -> bool:
    rc = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
    ).returncode
    return rc == 0


def invoke_opencode(worktree: Path, model: str, log_file: Path) -> int:
    """组装 brief + per-task prompt 一并喂给 opencode。"""
    combined = (
        BRIEF.read_text() + "\n\n---\n\n" +
        (worktree / ".codegen-prompt.md").read_text()
    )
    print(f"\n[codegen] invoking {model} ... 输出 → {log_file}")
    with open(log_file, "w") as logf:
        proc = subprocess.Popen(
            ["opencode", "run", "-m", model, combined],
            cwd=worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            logf.write(line)
            logf.flush()
            # 简化输出到终端（去 ANSI）
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).rstrip()
            if clean:
                print(f"  [agent] {clean[:140]}")
        return proc.wait()


def run_gates(worktree: Path, args: argparse.Namespace, smoke_task_id: int) -> dict:
    """跑 brief §4 全套验收门，返回 {gate: pass|fail}。"""
    res: dict[str, bool] = {}
    res["pytest_all"] = sh_ok(
        ["uv", "run", "pytest", "tests/", "-q"], cwd=worktree)
    res["pytest_new"] = sh_ok(
        ["uv", "run", "pytest",
         f"tests/{args.business_context}/test_adapter_{slug(args.host)}.py", "-v"],
        cwd=worktree)
    res["registry"] = sh_ok(
        ["uv", "run", "python", "-c",
         f"from infra import adapter_registry; "
         f"adapter_registry.discover(); "
         f"print(adapter_registry.get('{args.business_context}', '{args.host}'))"],
        cwd=worktree)
    smoke_db = worktree / "runtime/db/dev.db"
    if smoke_db.exists():
        smoke_db.unlink()
    # 清掉 WAL/SHM 文件，规避 sqlite 偶发 disk I/O error
    for stale in (worktree / "runtime/db").glob("dev.db-*"):
        stale.unlink()
    smoke_cmd = [
        "uv", "run", "python", "scripts/run_crawl_task.py",
        f"domains/{args.business_context}/seeds/{slug(args.host)}.yaml",
        "--max-pages", "30", "--max-depth", "1",
        "--scope-mode", args.scope_mode,
        "--task-id", str(smoke_task_id),
    ]
    res["live_smoke"] = sh_ok(smoke_cmd, cwd=worktree)
    if not res["live_smoke"]:
        # 偶发 sqlite I/O 错误重试一次
        print("[gate] live_smoke 失败，1 秒后重试一次")
        time.sleep(1)
        for stale in (worktree / "runtime/db").glob("dev.db*"):
            stale.unlink()
        res["live_smoke"] = sh_ok(smoke_cmd, cwd=worktree)
    res["audit"] = sh_ok(
        ["uv", "run", "python", "scripts/audit_crawl_quality.py",
         "--task-id", str(smoke_task_id),
         "--db", str(smoke_db)],
        cwd=worktree)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", required=True, help="例：www.most.gov.cn")
    ap.add_argument("--entry-url", required=True)
    ap.add_argument("--business-context", default="gov_policy")
    ap.add_argument(
        "--scope-mode", default="same_origin",
        choices=["same_origin", "same_etld_plus_one", "url_pattern", "allowlist"],
    )
    ap.add_argument("--model", default="opencode/minimax-m2.5-free",
                    help="opencode 模型 ID，可换 sonnet / opus / 其它")
    ap.add_argument("--worktree-base", default=str(REPO.parent),
                    help="worktree 父目录")
    ap.add_argument("--force", action="store_true",
                    help="worktree 已存在时清理重建")
    ap.add_argument("--smoke-task-id", type=int,
                    default=int(time.strftime("%H%M%S")))
    ap.add_argument("--skip-codegen", action="store_true",
                    help="只跑 gate（agent 产物已就位时调试用）")
    args = ap.parse_args()

    host_slug = slug(args.host)
    branch = f"agent/codegen-{host_slug}"
    worktree = Path(args.worktree_base) / f"xiniu-crawler-codegen-{host_slug}"
    log_file = REPO / f"runtime/codegen/{host_slug}-{int(time.time())}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== codegen for {args.host} ===")
    print(f"  business_context : {args.business_context}")
    print(f"  entry_url        : {args.entry_url}")
    print(f"  scope_mode       : {args.scope_mode}")
    print(f"  model            : {args.model}")
    print(f"  worktree         : {worktree}")
    print(f"  branch           : {branch}")
    print(f"  smoke task_id    : {args.smoke_task_id}")
    print(f"  log              : {log_file}")

    if not args.skip_codegen:
        setup_worktree(worktree, branch, args.force)
        write_per_task_prompt(worktree, args)
        rc = invoke_opencode(worktree, args.model, log_file)
        print(f"\n[codegen] opencode exit code: {rc}")
        if rc != 0:
            print("opencode 失败；worktree 留存供人工查 → ", worktree)

    # 跑验收门，无论 opencode 退出码如何（agent 退出码不可信）
    print("\n=== 验收门 ===")
    gates = run_gates(worktree, args, args.smoke_task_id)
    print("\n=== gate 结果 ===")
    for name, ok in gates.items():
        print(f"  {name:14s}: {'PASS' if ok else 'FAIL'}")

    overall = all(gates.values())
    verdict = "green" if overall else "red"
    print(f"\n=== 整体判定: {verdict.upper()} ===")
    print(f"\n下一步：")
    if overall:
        print(f"  1. 人工 review worktree: {worktree}")
        print(f"  2. 没问题就合回：")
        print(f"     git -C {REPO} merge {branch}")
        print(f"     git worktree remove {worktree}")
    else:
        print(f"  1. 看失败的 gate（上面 FAIL 行）")
        print(f"  2. 看 codegen 日志：{log_file}")
        print(f"  3. 看 worktree 里 agent 写的 eval：")
        print(f"     {worktree}/docs/eval-test/codegen-{host_slug}-*.md")
        print(f"  4. 修补 / 换 model / 换站点重跑")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
