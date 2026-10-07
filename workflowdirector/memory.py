"""Read-only memory instrumentation for WorkflowDirector.

This module deliberately does not unload models or mutate ComfyUI model state.
Phase 0 needs trustworthy measurements before Phase 2 experiments with a real
memory barrier.
"""

from __future__ import annotations

import os
from typing import Any

import torch

try:
    import psutil
except Exception:  # pragma: no cover - fallback for unusually small installs
    psutil = None


_GIB = 1024 ** 3


def _gib(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / _GIB, 4)


def memory_snapshot() -> dict[str, Any]:
    """Return a JSON-serializable snapshot of process and CUDA memory."""

    result: dict[str, Any] = {
        "pid": os.getpid(),
        "process_rss_gib": None,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda": None,
    }

    if psutil is not None:
        try:
            result["process_rss_gib"] = _gib(psutil.Process().memory_info().rss)
        except Exception:
            pass

    if not torch.cuda.is_available():
        return result

    try:
        device = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device)
        free_bytes, total_bytes = torch.cuda.mem_get_info(device)

        result["cuda"] = {
            "device_index": int(device),
            "device_name": props.name,
            "allocated_gib": _gib(torch.cuda.memory_allocated(device)),
            "reserved_gib": _gib(torch.cuda.memory_reserved(device)),
            "free_gib": _gib(free_bytes),
            "total_gib": _gib(total_bytes),
            "max_allocated_gib": _gib(torch.cuda.max_memory_allocated(device)),
            "max_reserved_gib": _gib(torch.cuda.max_memory_reserved(device)),
        }
    except Exception as exc:
        result["cuda"] = {
            "error": f"{type(exc).__name__}: {exc}",
        }

    return result


def compact_memory_line(snapshot: dict[str, Any] | None = None) -> str:
    """Format the fields useful during the lab into one console line."""

    snapshot = snapshot or memory_snapshot()
    rss = snapshot.get("process_rss_gib")
    cuda = snapshot.get("cuda")

    if not isinstance(cuda, dict) or "error" in cuda:
        return f"RAM RSS={rss!s} GiB | CUDA unavailable"

    return (
        f"RAM RSS={rss!s} GiB | "
        f"VRAM allocated={cuda.get('allocated_gib')} GiB | "
        f"reserved={cuda.get('reserved_gib')} GiB | "
        f"free={cuda.get('free_gib')} GiB / "
        f"{cuda.get('total_gib')} GiB"
    )
