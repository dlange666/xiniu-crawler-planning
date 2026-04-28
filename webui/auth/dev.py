"""Development auth backend."""

from __future__ import annotations

from starlette.requests import Request

from webui.auth.backend import User
from webui.config import WebuiConfig


class DevBackend:
    def __init__(self, config: WebuiConfig) -> None:
        self.config = config

    def current_user(self, request: Request) -> User:
        return User(sub="dev", email=self.config.dev_user, role=self.config.dev_role)

    def login_url(self, *, redirect_to: str) -> str:
        return redirect_to

    def logout_url(self, *, post_logout: str) -> str:
        return post_logout

