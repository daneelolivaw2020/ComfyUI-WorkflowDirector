"""HTTP routes for WorkflowDirector diagnostics and prepared runs."""

from __future__ import annotations

import json

from aiohttp import ContentTypeError, web
import comfyui_version
from server import PromptServer

from . import VERSION
from .core import ActiveRunError, DuplicateRunError, RunNotFoundError
from .memory import memory_snapshot
from .run_api import RunRequestError, parse_run_request
from .runtime import (
    BOUNDARY_MODE,
    effective_observation_window_seconds,
    get_director_service,
)


@PromptServer.instance.routes.get("/workflowdirector/health")
async def workflowdirector_health(_request):
    service_state = None
    window_seconds = None
    try:
        service = get_director_service()
        window_seconds = effective_observation_window_seconds()
        service_state = {
            "ready": True,
            "active_run_id": service.active_run_id,
        }
    except RuntimeError as exc:
        service_state = {
            "ready": False,
            "detail": str(exc),
        }

    return web.json_response(
        {
            "ok": True,
            "name": "ComfyUI-WorkflowDirector",
            "workflowdirector_version": VERSION,
            "comfyui_version": getattr(comfyui_version, "__version__", None),
            "director_service": service_state,
            "boundary_mode": BOUNDARY_MODE,
            "observation_window_seconds": window_seconds,
        }
    )


@PromptServer.instance.routes.get("/workflowdirector/memory")
async def workflowdirector_memory(_request):
    return web.json_response(memory_snapshot())


@PromptServer.instance.routes.post("/workflowdirector/runs")
async def workflowdirector_start_run(request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ContentTypeError):
        return web.json_response(
            {"ok": False, "error": "request body must be valid JSON"},
            status=400,
        )

    try:
        plan, client_id = parse_run_request(payload)
    except RunRequestError as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=400,
        )

    try:
        service = get_director_service()
        record = await service.start(
            plan,
            client_id=client_id,
        )
    except (ActiveRunError, DuplicateRunError) as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=409,
        )
    except RuntimeError as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=503,
        )

    return web.json_response(
        {
            "ok": True,
            "run_id": plan.run_id,
            "boundary_mode": BOUNDARY_MODE,
            "observation_window_seconds": effective_observation_window_seconds(),
            "record": record.to_dict(),
        },
        status=202,
    )


@PromptServer.instance.routes.get("/workflowdirector/runs/{run_id}")
async def workflowdirector_get_run(request):
    run_id = request.match_info["run_id"]

    try:
        service = get_director_service()
        record = service.get_record(run_id)
    except RunNotFoundError:
        return web.json_response(
            {"ok": False, "error": "run not found"},
            status=404,
        )
    except RuntimeError as exc:
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=503,
        )

    return web.json_response(
        {
            "ok": True,
            "active": service.active_run_id == run_id,
            "boundary_mode": BOUNDARY_MODE,
            "observation_window_seconds": effective_observation_window_seconds(),
            "record": record.to_dict(),
        }
    )
