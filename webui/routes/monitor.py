"""Monitoring pages and utility APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from infra import adapter_registry
from webui.auth.backend import User
from webui.auth.deps import require_role

router = APIRouter()
VIEWER = Depends(require_role("viewer"))


@router.get("/", response_class=HTMLResponse)
def home(request: Request, user: User = VIEWER):
    tasks = request.app.state.task_store.list_tasks(limit=20)["items"]
    return request.app.state.templates.TemplateResponse(
        request, "monitor/index.html", {"user": user, "tasks": tasks}
    )


@router.get("/monitor", response_class=HTMLResponse)
def monitor(request: Request, user: User = VIEWER):
    return request.app.state.templates.TemplateResponse(
        request, "monitor/monitor.html", {"user": user}
    )


@router.get("/adapters", response_class=HTMLResponse)
def adapters(request: Request, user: User = VIEWER):
    adapter_registry.discover()
    entries = adapter_registry.list_all()
    return request.app.state.templates.TemplateResponse(
        request,
        "monitor/adapters.html",
        {"user": user, "adapters": entries},
    )


@router.get("/api/adapters")
def api_adapters(user: User = VIEWER):
    _ = user
    adapter_registry.discover()
    return {
        "items": [
            {
                "business_context": e.business_context,
                "host": e.host,
                "data_kind": e.data_kind,
                "schema_version": e.schema_version,
                "render_mode": e.render_mode,
                "last_verified_at": e.last_verified_at.isoformat(),
                "module_path": e.module_path,
            }
            for e in adapter_registry.list_all()
        ]
    }


@router.get("/hosts", response_class=HTMLResponse)
def hosts(request: Request, user: User = VIEWER):
    tasks = request.app.state.task_store.list_tasks(limit=100)["items"]
    hosts = sorted({t["host"] for t in tasks})
    return request.app.state.templates.TemplateResponse(
        request, "monitor/hosts.html", {"user": user, "hosts": hosts}
    )


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/version")
def version():
    return {"service": "xiniu-crawler-webui", "spec": "webui.md rev 6"}
