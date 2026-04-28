"""Test auth backend."""

from __future__ import annotations

from starlette.requests import Request

from webui.auth.backend import User


class MockBackend:
    def __init__(self, user: User) -> None:
        self.user = user

    def current_user(self, request: Request) -> User:
        return self.user

    def login_url(self, *, redirect_to: str) -> str:
        return redirect_to

    def logout_url(self, *, post_logout: str) -> str:
        return post_logout

