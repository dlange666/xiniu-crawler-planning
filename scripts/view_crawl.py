#!/usr/bin/env python3
"""查看采集结果。

用法：
  uv run python scripts/view_crawl.py                       # 列表全部
  uv run python scripts/view_crawl.py --task 1001           # 仅某个 task
  uv run python scripts/view_crawl.py --id 1                # 看单条详情
  uv run python scripts/view_crawl.py --id 1 --raw          # 看原始 HTML
  uv run python scripts/view_crawl.py --id 1 --open         # 浏览器打开原始 HTML

环境变量：
  CRAWLER_DB_PATH        默认 runtime/db/dev.db
  CRAWLER_BLOB_ROOT      默认 runtime/raw （仅 --raw/--open 用）
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse


def open_db() -> sqlite3.Connection:
    db_path = os.environ.get("CRAWLER_DB_PATH", "runtime/db/dev.db")
    if not Path(db_path).exists():
        print(f"❌ DB 不存在: {db_path}", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_records(conn: sqlite3.Connection, *, task_id: int | None = None) -> None:
    sql = """
        SELECT id, task_id, business_context, host,
               json_extract(data, '$.title') AS title,
               substr(content_sha256, 1, 12) AS sha,
               substr(created_at, 1, 19) AS created
        FROM crawl_raw
    """
    params: tuple = ()
    if task_id is not None:
        sql += " WHERE task_id = ?"
        params = (task_id,)
    sql += " ORDER BY id"

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("(no records)")
        return

    print(f"\n📚 共 {len(rows)} 条采集记录\n")
    print(f"{'id':>4}  {'task_id':>8}  {'host':<22}  sha       title")
    print("-" * 100)
    for r in rows:
        title = (r["title"] or "(no title)")[:50]
        print(f"{r['id']:>4}  {r['task_id']:>8}  {r['host']:<22}  {r['sha']}…  {title}")


def show_detail(conn: sqlite3.Connection, record_id: int) -> None:
    row = conn.execute(
        "SELECT * FROM crawl_raw WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        print(f"❌ id={record_id} 不存在", file=sys.stderr)
        sys.exit(2)

    data = json.loads(row["data"])

    print()
    print("=" * 80)
    print(f"  id              = {row['id']}")
    print(f"  task_id         = {row['task_id']}")
    print(f"  business_context= {row['business_context']}")
    print(f"  host            = {row['host']}")
    print(f"  url             = {row['url']}")
    print(f"  url_hash        = {row['url_hash']}")
    print(f"  content_sha256  = {row['content_sha256']}")
    print(f"  raw_blob_uri    = {row['raw_blob_uri']}")
    print(f"  created_at      = {row['created_at']}")
    print("=" * 80)
    print()
    print(f"  📌 标题：{data.get('title', '(无)')}")
    print()
    print("  📅 元数据：")
    for k, v in (data.get("source_metadata") or {}).items():
        print(f"    {k}: {v.strip()}")
    print()

    body = data.get("body_text", "")
    print(f"  📄 正文（前 800 字符 / 共 {len(body)} 字符）：")
    print()
    wrap_width = 78
    indent = "    "
    for line in body[:800].split("\n"):
        if not line.strip():
            print()
            continue
        for chunk in textwrap.wrap(line, wrap_width):
            print(f"{indent}{chunk}")
    if len(body) > 800:
        print()
        print(f"    … （省略 {len(body) - 800} 字符；用 --raw 看原始 HTML）")
    print()

    atts = data.get("attachments") or []
    if atts:
        print(f"  📎 附件 {len(atts)} 个：")
        for a in atts:
            print(f"    - {a.get('filename') or '(unnamed)'}: {a['url']}")
        print()


def show_raw(conn: sqlite3.Connection, record_id: int, *, action: str = "print") -> None:
    """action ∈ {'print', 'open'}"""
    row = conn.execute(
        "SELECT raw_blob_uri, url, host FROM crawl_raw WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        print(f"❌ id={record_id} 不存在", file=sys.stderr)
        sys.exit(2)

    uri = row["raw_blob_uri"]
    if not uri.startswith("file://"):
        print(f"❌ raw_blob_uri 不是 file://: {uri}", file=sys.stderr)
        sys.exit(2)
    path = uri[len("file://"):]
    if not Path(path).exists():
        print(f"❌ 原始 blob 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)

    print(f"📦 原始 HTML：{path}（来源 URL: {row['url']}）")

    if action == "open":
        # macOS open；其它平台用户自行 cat
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
            print("   已在浏览器打开")
        else:
            print(f"   非 macOS，请手动打开：{path}")
    elif action == "print":
        size = Path(path).stat().st_size
        print(f"   大小 {size} 字节；前 1500 字符预览：\n")
        with open(path, encoding="utf-8", errors="replace") as f:
            print(f.read(1500))
        if size > 1500:
            print(f"\n... (省略 {size - 1500} 字节)")


def main() -> int:
    parser = argparse.ArgumentParser(description="查看采集结果")
    parser.add_argument("--task", type=int, default=None, help="按 task_id 过滤")
    parser.add_argument("--id", type=int, default=None, help="看某条详情")
    parser.add_argument("--raw", action="store_true", help="打印原始 HTML（与 --id 配合）")
    parser.add_argument("--open", action="store_true", help="在浏览器打开原始 HTML（macOS）")
    args = parser.parse_args()

    conn = open_db()
    try:
        if args.id is not None:
            if args.open:
                show_raw(conn, args.id, action="open")
            elif args.raw:
                show_raw(conn, args.id, action="print")
            else:
                show_detail(conn, args.id)
        else:
            list_records(conn, task_id=args.task)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
