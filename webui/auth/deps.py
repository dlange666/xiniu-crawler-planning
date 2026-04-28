"""FastAPI auth dependencies."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request

from webui.auth.backend import User
from webui.auth.roles import has_role


def current_user(request: Request) -> User:
    return request.app.state.auth_backend.current_user(request)


def require_role(role: str) -> Callable[[Request], User]:
    def _dependency(request: Request) -> User:
        user = current_user(request)
        if not has_role(user.role, role):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return _dependency

