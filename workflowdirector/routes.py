"""HTTP routes for WorkflowDirector diagnostics and prepared runs."""

from __future__ import annotations

import json
import asyncio
import ipaddress

from aiohttp import ContentTypeError, web
import comfyui_version
from server import PromptServer

from . import VERSION
from .core import ActiveRunError, DuplicateRunError, RunNotFoundError
from .memory import memory_snapshot
from .allocator_diagnostics import (
    AllocatorDiagnosticsError,
    capture_allocator,
    enabled as glibc_diagnostics_enabled,
)
from .memory_analysis import summarize_run_memory
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
            "memory_summary": summarize_run_memory(record),
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
            "memory_summary": summarize_run_memory(record),
        }
    )


# This route is not registered at all unless explicitly enabled at startup.
# It is intentionally different from the always-on read-only /memory route.
if glibc_diagnostics_enabled():
    @PromptServer.instance.routes.get("/workflowdirector/memory/glibc")
    async def workflowdirector_glibc_diagnostics(request):
        # Default Colab launches Comfy with --listen 127.0.0.1. Reject
        # non-local direct clients as additional defense, not authentication.
        try:
            remote_is_local = ipaddress.ip_address(request.remote or "").is_loopback
        except ValueError:
            remote_is_local = False
        if not remote_is_local:
            return web.json_response({"ok": False, "error": "loopback only"}, status=403)

        # WorkflowDirector active_run_id alone does not detect manual Comfy jobs.
        # Verify the native Comfy prompt queue (running AND pending) too.
        queue = getattr(PromptServer.instance, "prompt_queue", None)
        try:
            director = get_director_service()
            busy = (
                queue is None
                or queue.get_tasks_remaining() != 0
                or director.active_run_id is not None
            )
        except (RuntimeError, AttributeError):
            return web.json_response(
                {"ok": False, "error": "unable to verify idle state"}, status=503
            )
        if busy:
            return web.json_response(
                {"ok": False, "error": "ComfyUI or Director is busy"}, status=409
            )

        try:
            # Do not hold up aiohttp event loop during stdio XML generation.
            # Still a native diagnostic in THIS Comfy PID, not the Colab notebook.
            result = await asyncio.to_thread(capture_allocator)
        except (AllocatorDiagnosticsError, OSError) as exc:
            return web.json_response(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                status=503,
            )

        # A direct UI job could start between the pre-check and the snapshot.
        # Reject potentially contaminated results rather than claiming idle.
        if queue.get_tasks_remaining() != 0 or director.active_run_id is not None:
            return web.json_response(
                {"ok": False, "error": "job started during sampling"}, status=409
            )
        return web.json_response({"ok": True, "snapshot": result})
