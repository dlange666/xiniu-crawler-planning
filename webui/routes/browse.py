"""crawl_raw result browser."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from webui.auth.backend import User
from webui.auth.deps import require_role

router = APIRouter()
VIEWER = Depends(require_role("viewer"))


@router.get("/browse")
def browse_home(request: Request, user: User = VIEWER):
    _ = user
    tasks = request.app.state.task_store.list_tasks(limit=1)["items"]
    if not tasks:
        return RedirectResponse("/tasks", status_code=303)
    return RedirectResponse(f"/tasks/{tasks[0]['task_id']}/items", status_code=303)


@router.get("/tasks/{task_id}/items", response_class=HTMLResponse)
def task_items(
    task_id: int,
    request: Request,
    offset: int = 0,
    user: User = VIEWER,
):
    task = request.app.state.task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    items = request.app.state.task_store.list_items(task_id, offset=offset)
    return request.app.state.templates.TemplateResponse(
        request,
        "browse/items.html",
        {
            "user": user,
            "task": task,
            "items": items,
            "offset": offset,
        },
    )


@router.get("/tasks/{task_id}/items/{item_id}", response_class=HTMLResponse)
def task_item_detail(
    task_id: int,
    item_id: int,
    request: Request,
    user: User = VIEWER,
):
    task = request.app.state.task_store.get_task(task_id)
    item = request.app.state.task_store.get_item(task_id, item_id)
    if task is None or item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "browse/item_detail.html",
        {"user": user, "task": task, "item": item},
    )


@router.get("/api/tasks/{task_id}/items/{item_id}")
def api_task_item_detail(
    task_id: int,
    item_id: int,
    request: Request,
    user: User = VIEWER,
):
    _ = user
    task = request.app.state.task_store.get_task(task_id)
    item = request.app.state.task_store.get_item(task_id, item_id)
    if task is None or item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"task": task, "item": item}
