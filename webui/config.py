"""WebUI runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebuiConfig:
    db_path: Path = Path("runtime/db/dev.db")
    auth_mode: str = "dev"
    env: str = "development"
    dev_user: str = "operator@local"
    dev_role: str = "operator"
    bind: str = "127.0.0.1"
    port: int = 8765
    session_secret: str = "dev-session-secret-change-me"

    @classmethod
    def from_env(cls) -> WebuiConfig:
        return cls(
            db_path=Path(os.environ.get("CRAWLER_DB_PATH", "runtime/db/dev.db")),
            auth_mode=os.environ.get("WEBUI_AUTH_MODE", "dev"),
            env=os.environ.get("WEBUI_ENV", "development"),
            dev_user=os.environ.get("WEBUI_DEV_USER", "operator@local"),
            dev_role=os.environ.get("WEBUI_DEV_ROLE", "operator"),
            bind=os.environ.get("WEBUI_BIND", "127.0.0.1"),
            port=int(os.environ.get("WEBUI_PORT", "8765")),
            session_secret=os.environ.get(
                "WEBUI_SESSION_SECRET", "dev-session-secret-change-me"
            ),
        )

    def validate(self) -> None:
        if self.auth_mode != "dev":
            raise NotImplementedError("WEBUI_AUTH_MODE=oauth is tracked by TD-018")
        if self.env == "production" and self.auth_mode == "dev":
            raise RuntimeError("WEBUI_ENV=production forbids WEBUI_AUTH_MODE=dev")
        if self.dev_role not in {"viewer", "operator", "admin"}:
            raise ValueError("WEBUI_DEV_ROLE must be viewer, operator, or admin")
