"""Auth backend protocol and user model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from starlette.requests import Request


@dataclass(frozen=True)
class User:
    sub: str
    email: str
    role: str


class AuthBackend(Protocol):
    def current_user(self, request: Request) -> User: ...

    def login_url(self, *, redirect_to: str) -> str: ...

    def logout_url(self, *, post_logout: str) -> str: ...

