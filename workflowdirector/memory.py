"""Read-only memory instrumentation for WorkflowDirector.

Phase 0 must measure memory without changing ComfyUI model state. The values
below deliberately distinguish process RAM, cgroup-aware system RAM, PyTorch's
CUDA allocator, and device-global CUDA memory.
"""

from __future__ import annotations

import os
from typing import Any

import psutil
import torch

import comfy.system_memory


_GIB = 1024 ** 3


def _gib(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / _GIB, 4)


def memory_snapshot() -> dict[str, Any]:
    """Return a JSON-serializable, read-only memory snapshot."""

    process_rss = psutil.Process().memory_info().rss
    system_total = comfy.system_memory.virtual_memory_total()
    system_available = comfy.system_memory.virtual_memory_available()

    result: dict[str, Any] = {
        "pid": os.getpid(),
        "process_rss_gib": _gib(process_rss),
        "system_ram": {
            "total_gib": _gib(system_total),
            "available_gib": _gib(system_available),
            "unavailable_gib": _gib(max(0, system_total - system_available)),
        },
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda": None,
    }

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
            "peak_allocated_since_reset_gib": _gib(
                torch.cuda.max_memory_allocated(device)
            ),
            "peak_reserved_since_reset_gib": _gib(
                torch.cuda.max_memory_reserved(device)
            ),
            "device_free_gib": _gib(free_bytes),
            "device_used_gib": _gib(max(0, total_bytes - free_bytes)),
            "device_total_gib": _gib(total_bytes),
        }
    except Exception as exc:
        result["cuda"] = {
            "error": f"{type(exc).__name__}: {exc}",
        }

    return result


def compact_memory_line(snapshot: dict[str, Any] | None = None) -> str:
    """Format the fields most useful while watching the laboratory console."""

    snapshot = snapshot or memory_snapshot()
    rss = snapshot.get("process_rss_gib")
    system_ram = snapshot.get("system_ram") or {}
    cuda = snapshot.get("cuda")

    ram_text = (
        f"RAM RSS={rss!s} GiB | "
        f"system available={system_ram.get('available_gib')} / "
        f"{system_ram.get('total_gib')} GiB"
    )

    if not isinstance(cuda, dict):
        return f"{ram_text} | CUDA unavailable"

    if "error" in cuda:
        return f"{ram_text} | CUDA error={cuda['error']}"

    return (
        f"{ram_text} | "
        f"VRAM torch allocated={cuda.get('allocated_gib')} GiB | "
        f"reserved={cuda.get('reserved_gib')} GiB | "
        f"device used={cuda.get('device_used_gib')} GiB | "
        f"free={cuda.get('device_free_gib')} / "
        f"{cuda.get('device_total_gib')} GiB"
    )
