"""Lazy wiring of WorkflowDirector core to the running Comfy server."""

from __future__ import annotations

import os

from server import PromptServer

from .boundary import ObservationBoundary, SnapshotRunObserver
from .comfy_http import ComfyHttpAdapter
from .core import DirectorEngine, DirectorRunService
from .memory import memory_snapshot


_service: DirectorRunService | None = None
_observation_window_used: float | None = None

BOUNDARY_MODE = "observe-phase2-nondestructive"
_DEFAULT_OBSERVATION_WINDOW_SECONDS = 1.0


def observation_window_seconds() -> float:
    raw = os.environ.get(
        "WORKFLOWDIRECTOR_OBSERVATION_SECONDS",
        str(_DEFAULT_OBSERVATION_WINDOW_SECONDS),
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            "WORKFLOWDIRECTOR_OBSERVATION_SECONDS must be a number"
        ) from exc

    if value < 0:
        raise RuntimeError(
            "WORKFLOWDIRECTOR_OBSERVATION_SECONDS must be >= 0"
        )
    return value


def effective_observation_window_seconds() -> float:
    if _observation_window_used is not None:
        return _observation_window_used
    return observation_window_seconds()


def get_director_service() -> DirectorRunService:
    global _service, _observation_window_used

    if _service is not None:
        return _service

    server = PromptServer.instance
    session = getattr(server, "client_session", None)
    port = getattr(server, "port", None)

    if session is None:
        raise RuntimeError("Comfy HTTP client session is not ready")
    if port is None:
        raise RuntimeError("Comfy server port is not available yet")

    # Mandatory acceptance target is the standard local Colab Comfy process.
    # 127.0.0.1 works for the normal default bind and for 0.0.0.0 binds.
    base_url = f"http://127.0.0.1:{int(port)}"

    adapter = ComfyHttpAdapter(
        base_url=base_url,
        session=session,
    )
    run_observer = SnapshotRunObserver(
        snapshot=memory_snapshot,
        warm_up=True,
    )
    window_seconds = observation_window_seconds()
    boundary_observer = ObservationBoundary(
        snapshot=memory_snapshot,
        observation_window_seconds=window_seconds,
        sample_interval_seconds=0.25,
        active_jobs=adapter.get_active_job_ids,
    )
    engine = DirectorEngine(
        adapter,
        run_observer=run_observer,
        boundary_observer=boundary_observer,
    )
    _service = DirectorRunService(engine)
    _observation_window_used = window_seconds
    return _service
