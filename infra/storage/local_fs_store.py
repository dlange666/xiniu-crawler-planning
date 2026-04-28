"""本地文件系统 BlobStore（dev profile）。

按 dev profile 把原始字节落到 runtime/raw/<key>。
prod profile 走阿里云 OSS（暂未实现）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class LocalFsBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 防御性：禁止 .. 跳出 root
        p = (self.root / key).resolve()
        root_resolved = self.root.resolve()
        if root_resolved not in p.parents and p != root_resolved:
            msg = f"key escapes blob root: {key!r}"
            raise ValueError(msg)
        return p

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        del content_type  # 本地 FS 不记 metadata；prod OSS 实现会用
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"file://{target}"

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def stat(self, key: str) -> dict[str, Any]:
        p = self._path(key)
        s = p.stat()
        return {"size": s.st_size, "mtime": s.st_mtime}
