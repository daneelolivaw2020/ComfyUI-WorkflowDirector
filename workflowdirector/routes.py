"""Small diagnostic HTTP routes for the WorkflowDirector lab."""

from __future__ import annotations

from aiohttp import web
from server import PromptServer

from . import VERSION
from .memory import memory_snapshot


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
