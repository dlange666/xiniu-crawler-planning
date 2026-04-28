"""FastAPI application factory for WebUI."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, HTMLResponse, Response

from webui.auth.dev import DevBackend
from webui.config import WebuiConfig
from webui.routes import browse, monitor, tasks
from webui.stores.audit_store import AuditStore
from webui.stores.task_store import TaskStore

PACKAGE_ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = PACKAGE_ROOT / "frontend" / "dist"


def create_app(config: WebuiConfig | None = None) -> FastAPI:
    config = config or WebuiConfig.from_env()
    config.validate()

    app = FastAPI(title="xiniu-crawler WebUI")
    app.state.config = config
    app.state.auth_backend = DevBackend(config)
    app.state.task_store = TaskStore(config.db_path)
    app.state.audit_store = AuditStore(config.db_path)
    app.state.templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))

    app.add_middleware(SessionMiddleware, secret_key=config.session_secret)
    app.middleware("http")(audit_middleware)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")

    app.include_router(monitor.router)
    app.include_router(tasks.router)
    app.include_router(browse.router)
    _mount_react_spa(app)
    return app


async def audit_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or uuid4().hex
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 500:
        user = request.app.state.auth_backend.current_user(request)
        action, target_type, target_id = _audit_target(request)
        request.app.state.audit_store.insert(
            actor=user.email or user.sub,
            role=user.role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_id=request_id,
        )
    response.headers["x-request-id"] = request_id
    return response


def _audit_target(request: Request) -> tuple[str, str | None, str | None]:
    path = request.url.path
    if path in {"/tasks", "/api/tasks"} and request.method == "POST":
        return "submit_task", "task", None
    if path.startswith("/api/tasks/") and path.endswith("/cancel"):
        parts = path.strip("/").split("/")
        return "cancel_task", "task", parts[2] if len(parts) > 2 else None
    return "webui_write", None, None


def _mount_react_spa(app: FastAPI) -> None:
    index_html = FRONTEND_DIST / "index.html"
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/{path:path}", include_in_schema=False)
    def react_spa(path: str = ""):
        _ = path
        if index_html.exists():
            return FileResponse(index_html)
        return HTMLResponse(
            "<!doctype html><title>WebUI frontend</title>"
            "<main style='font-family:-apple-system;padding:32px'>"
            "<h1>React frontend is not built</h1>"
            "<p>Run <code>cd webui/frontend && npm install && npm run build</code>, "
            "or use <code>npm run dev</code> for Vite development.</p>"
            "</main>",
            status_code=503,
        )


app = create_app()
