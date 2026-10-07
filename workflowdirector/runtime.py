"""Lazy wiring of WorkflowDirector core to the running Comfy server."""

from __future__ import annotations

from server import PromptServer

from .comfy_http import ComfyHttpAdapter
from .core import DirectorEngine, DirectorRunService


_service: DirectorRunService | None = None


def get_director_service() -> DirectorRunService:
    global _service

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
    engine = DirectorEngine(adapter)
    _service = DirectorRunService(engine)
    return _service
