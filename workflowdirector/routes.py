"""Small read-only diagnostic HTTP routes for the WorkflowDirector lab."""

from __future__ import annotations

from aiohttp import web
from server import PromptServer

from . import VERSION
from .memory import memory_snapshot


def _prompt_ids(items):
    """Extract prompt ids without exposing prompt payloads or extra data."""

    ids = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            ids.append(item[1])
    return ids


@PromptServer.instance.routes.get("/workflowdirector/health")
async def workflowdirector_health(_request):
    return web.json_response(
        {
            "ok": True,
            "name": "ComfyUI-WorkflowDirector",
            "version": VERSION,
        }
    )


@PromptServer.instance.routes.get("/workflowdirector/memory")
async def workflowdirector_memory(_request):
    return web.json_response(memory_snapshot())


@PromptServer.instance.routes.get("/workflowdirector/status")
async def workflowdirector_status(_request):
    running, pending = PromptServer.instance.prompt_queue.get_current_queue_volatile()
    running_ids = _prompt_ids(running)
    pending_ids = _prompt_ids(pending)

    return web.json_response(
        {
            "ok": True,
            "version": VERSION,
            "worker_idle": len(running_ids) == 0,
            "queue_empty": len(running_ids) == 0 and len(pending_ids) == 0,
            "running_prompt_ids": running_ids,
            "pending_prompt_ids": pending_ids,
            "memory": memory_snapshot(),
        }
    )
