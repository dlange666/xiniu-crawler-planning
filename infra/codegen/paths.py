"""Codegen 相关的 slug 与产物路径计算。"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def slug(host: str) -> str:
    """Return adapter slug identifying the source, not the delivery channel.

    www.most.gov.cn -> most；wap.miit.gov.cn -> miit；search.sh.gov.cn -> sh_search。
    """
    labels = [label for label in host.lower().split(".") if label]
    if not labels:
        return "unknown"

    service_prefixes = {"www", "wap", "m", "mobile"}
    searchable_prefixes = {"search", "sousuo"}
    suffixes = {
        ("gov", "cn"), ("com", "cn"), ("org", "cn"),
        ("net", "cn"), ("edu", "cn"), ("ac", "cn"),
    }
    removed_suffix: tuple[str, ...] = ()
    if len(labels) >= 2 and tuple(labels[-2:]) in suffixes:
        removed_suffix = tuple(labels[-2:])
        labels = labels[:-2]
    elif len(labels) >= 1:
        removed_suffix = (labels[-1],)
        labels = labels[:-1]

    dropped: list[str] = []
    while labels and labels[0] in service_prefixes | searchable_prefixes:
        dropped.append(labels.pop(0))

    if not labels and removed_suffix == ("gov", "cn"):
        labels = ["gov"]
    elif not labels:
        labels = [label for label in host.lower().split(".") if label][:1]

    source = labels[0]
    if any(prefix in searchable_prefixes for prefix in dropped):
        source = f"{source}_search"
    return re.sub(r"[^a-z0-9]+", "_", source).strip("_") or "unknown"


def context_spec_name(business_context: str) -> str:
    """gov_policy -> domain-gov-policy.md。"""
    return f"domain-{business_context.replace('_', '-')}.md"


def source_dir(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / "domains" / args.business_context / slug(args.host)


def adapter_artifact(worktree: Path, args: argparse.Namespace) -> Path:
    return source_dir(worktree, args) / f"{slug(args.host)}_adapter.py"


def seed_artifact(worktree: Path, args: argparse.Namespace) -> Path:
    return source_dir(worktree, args) / f"{slug(args.host)}_seed.yaml"


def adapter_test_artifact(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / "tests" / args.business_context / f"test_{slug(args.host)}_adapter.py"


def task_artifact_path(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / f"docs/task/active/task-codegen-{slug(args.host)}-{date.today()}.json"


def eval_artifact_path(worktree: Path, args: argparse.Namespace) -> Path:
    return worktree / f"docs/eval-test/codegen-{slug(args.host)}-{date.today():%Y%m%d}.md"


def plan_artifact_path(worktree: Path, args: argparse.Namespace) -> Path:
    return (
        worktree
        / f"docs/exec-plan/active/plan-{date.today():%Y%m%d}-codegen-{slug(args.host)}.md"
    )
