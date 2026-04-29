"""Task backend pages and APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from infra import adapter_registry
from webui.auth.backend import User
from webui.auth.deps import require_role

router = APIRouter()
VIEWER = Depends(require_role("viewer"))
OPERATOR = Depends(require_role("operator"))


@router.get("/tasks", response_class=HTMLResponse)
def task_list(request: Request, user: User = VIEWER):
    tasks = request.app.state.task_store.list_tasks()["items"]
    return request.app.state.templates.TemplateResponse(
        request, "tasks/list.html", {"user": user, "tasks": tasks}
    )


@router.get("/tasks/new", response_class=HTMLResponse)
def new_task(request: Request, user: User = OPERATOR):
    return request.app.state.templates.TemplateResponse(
        request, "tasks/new.html", {"user": user}
    )


@router.post("/tasks")
def create_task_from_form(
    request: Request,
    user: User = OPERATOR,
    business_context: str = Form("gov_policy"),
    site_url: str = Form(...),
    data_kind: str = Form("policy"),
    crawl_mode: str = Form("full"),
    scope_mode: str = Form("same_origin"),
    scope_url_pattern: str = Form(""),
    max_pages_per_run: str = Form(""),
    politeness_rps: str = Form("1.0"),
    purpose: str = Form(""),
    responsible_party: str = Form(""),
):
    task_id = request.app.state.task_store.create_task(
        {
            "business_context": business_context,
            "site_url": site_url,
            "data_kind": data_kind,
            "crawl_mode": crawl_mode,
            "scope_mode": scope_mode,
            "scope_url_pattern": scope_url_pattern,
            "max_pages_per_run": max_pages_per_run,
            "politeness_rps": politeness_rps,
            "purpose": purpose,
            "responsible_party": responsible_party,
        },
        actor=user.email,
    )
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(
    task_id: int,
    request: Request,
    url_offset: int = 0,
    url_limit: int = 50,
    user: User = VIEWER,
):
    task = request.app.state.task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    url_limit = max(1, min(url_limit, 100))
    url_offset = max(0, url_offset)
    progress = request.app.state.task_store.progress(task_id)
    url_total = request.app.state.task_store.count_url_records(task_id)
    urls = request.app.state.task_store.list_url_records(
        task_id, limit=url_limit, offset=url_offset
    )
    depth_summary = request.app.state.task_store.depth_summary(task_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "tasks/detail.html",
        {
            "user": user,
            "task": task,
            "progress": progress,
            "urls": urls,
            "url_total": url_total,
            "url_limit": url_limit,
            "url_offset": url_offset,
            "depth_summary": depth_summary,
        },
    )


@router.get("/api/tasks")
def api_tasks(
    request: Request,
    status: str | None = None,
    business_context: str | None = None,
    generation_status: str | None = None,
    adapter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = VIEWER,
):
    """服务端分页 + 三层状态筛选。

    - status: crawl_task_execution.status（爬取/调度状态）
    - generation_status: crawl_task_generation.status（codegen 过程）
    - adapter: all / ready / pending（基于 adapter_registry 的 host 集合）
    - business_context: 业务域过滤
    - page / page_size: 服务端分页，size 上限 100
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    adapter_registry.discover()
    known_hosts = {(e.business_context, e.host) for e in adapter_registry.list_all()}

    result = request.app.state.task_store.list_tasks(
        status=status,
        business_context=business_context,
        generation_status=generation_status,
        ready_hosts=known_hosts,
        adapter_filter=adapter,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    items = result["items"]
    for item in items:
        item["adapter_ready"] = (
            (item.get("business_context"), item.get("host")) in known_hosts
        )
    return {
        "items": items,
        "total": result["total"],
        "page": page,
        "page_size": page_size,
        "user": {"email": user.email, "role": user.role},
    }


@router.get("/api/tasks/{task_id}")
def api_task_detail(
    task_id: int,
    request: Request,
    user: User = VIEWER,
):
    _ = user
    task = request.app.state.task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    adapter_registry.discover()
    known_hosts = {(e.business_context, e.host) for e in adapter_registry.list_all()}
    task["adapter_ready"] = (task.get("business_context"), task.get("host")) in known_hosts
    task["generation_status"] = request.app.state.task_store.get_generation_status(task_id)

    return {
        "task": task,
        "progress": request.app.state.task_store.progress(task_id),
        "depth_summary": request.app.state.task_store.depth_summary(task_id),
        "fetched_depth_summary": request.app.state.task_store.depth_summary(
            task_id, kind="fetched"
        ),
        "jump_depth_summary": request.app.state.task_store.depth_summary(task_id, kind="jump"),
        "url_total": request.app.state.task_store.count_url_records(task_id),
        "fetched_total": request.app.state.task_store.count_url_records(
            task_id, kind="fetched"
        ),
        "jump_total": request.app.state.task_store.count_url_records(task_id, kind="jump"),
    }


@router.post("/api/tasks")
async def api_create_task(
    request: Request,
    user: User = OPERATOR,
):
    data = await request.json()
    task_id = request.app.state.task_store.create_task(data, actor=user.email)
    return {"task_id": task_id, "status": "scheduled"}


@router.post("/api/tasks/{task_id}/cancel")
def api_cancel_task(
    task_id: int,
    request: Request,
    user: User = OPERATOR,
):
    task = request.app.state.task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    request.app.state.task_store.cancel_task(task_id)
    return {"task_id": task_id, "status": "disabled"}


@router.get("/api/tasks/{task_id}/timeseries")
def api_task_timeseries(
    task_id: int,
    request: Request,
    metric: str = "fetches",
    user: User = VIEWER,
):
    _ = user, metric
    return request.app.state.task_store.timeseries(task_id)


@router.get("/api/tasks/{task_id}/urls")
def api_task_urls(
    task_id: int,
    request: Request,
    kind: str = "all",
    depth: int | None = None,
    limit: int = 200,
    offset: int = 0,
    user: User = VIEWER,
):
    _ = user
    if kind not in {"all", "collected", "uncollected", "fetched", "jump"}:
        raise HTTPException(
            status_code=400,
            detail="kind must be all, collected, uncollected, fetched, or jump",
        )
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return {
        "items": request.app.state.task_store.list_url_records(
            task_id, kind=kind, depth=depth, limit=limit, offset=offset
        ),
        "total": request.app.state.task_store.count_url_records(
            task_id, kind=kind, depth=depth
        ),
        "limit": limit,
        "offset": offset,
        "kind": kind,
        "depth": depth,
        "depth_summary": request.app.state.task_store.depth_summary(task_id, kind=kind),
    }
