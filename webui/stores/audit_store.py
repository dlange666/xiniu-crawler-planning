"""Audit writes for WebUI actions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class AuditStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def insert(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        target_type: str | None,
        target_id: str | None,
        payload: dict[str, Any],
        ip: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """INSERT INTO webui_audit
                    (actor, role, action, target_type, target_id, payload,
                     ip, user_agent, request_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        actor,
                        role,
                        action,
                        target_type,
                        target_id,
                        json.dumps(payload, ensure_ascii=False),
                        ip,
                        user_agent,
                        request_id,
                    ),
                )
        finally:
            conn.close()

