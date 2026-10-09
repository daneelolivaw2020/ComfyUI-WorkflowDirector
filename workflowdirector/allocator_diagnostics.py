"""Opt-in, idle-only diagnostic of glibc's malloc arenas.

This does not unload models, trim arenas, change allocator tunables, import torch,
or inspect model objects. It must run IN the ComfyUI process. Unlike a smaps
snapshot, malloc_info reports allocator-internal free-list totals; it does NOT
prove how many resident pages can be returned to the operating system.
"""

from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import os
import platform
import tempfile
import xml.etree.ElementTree as ET

from .proc_memory import process_smaps_rollup

MAX_XML_BYTES = 2 * 1024 * 1024
ENV_ENABLE = "WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS"


class AllocatorDiagnosticsError(RuntimeError):
    pass


def enabled() -> bool:
    """Only an explicit opt-in string enables the endpoint at startup."""
    return os.environ.get(ENV_ENABLE) == "1"


def parse_malloc_info(xml: bytes) -> dict:
    """Aggregate top-level glibc totals without double-counting heap children.

    The <malloc> root exposes summary totals; each <heap> also exposes its own
    totals. These must NOT be summed together. Tcache and other native allocators
    are not necessarily reported as glibc free-list bytes.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise AllocatorDiagnosticsError("glibc produced invalid allocator XML") from exc
    if root.tag != "malloc":
        raise AllocatorDiagnosticsError("unexpected allocator XML root")

    def measure(tag: str, type_name: str, attr: str) -> int | None:
        for child in root:
            if child.tag == tag and child.attrib.get("type") == type_name:
                try:
                    n = int(child.attrib[attr])
                except (KeyError, TypeError, ValueError) as exc:
                    raise AllocatorDiagnosticsError("missing or invalid allocator counter") from exc
                if n < 0:
                    raise AllocatorDiagnosticsError("negative allocator counter")
                return n
        return None

    required = {
        "arena_system_current_bytes": measure("system", "current", "size"),
        "arena_system_max_bytes": measure("system", "max", "size"),
        "free_fast_bytes": measure("total", "fast", "size"),
        "free_rest_bytes": measure("total", "rest", "size"),
        "direct_mmap_bytes": measure("total", "mmap", "size"),
        "direct_mmap_count": measure("total", "mmap", "count"),
    }
    if any(v is None for v in required.values()):
        raise AllocatorDiagnosticsError("incomplete glibc malloc_info XML")
    heaps = root.findall("heap")
    return {
        "heap_entries": len(heaps),
        **required,
        "free_list_estimate_bytes": required["free_fast_bytes"] + required["free_rest_bytes"],
        "limitations": [
            "heap_entries are allocator arena records, not the number of smaps mappings",
            "free-list bytes are not necessarily resident, reclaimable or safe to trim",
            "thread-local tcache and allocations by other runtimes may not appear as free",
            "arena_system_current is virtual allocator space, not process RSS",
        ],
    }


def _capture_glibc_xml(max_bytes: int = MAX_XML_BYTES) -> tuple[bytes, str]:
    """Write malloc_info to a private temporary FILE* via glibc, never stdout.

    fdopen owns only the duplicated file descriptor. The Python temporary file
    remains open for bounded reading, and all native handles are closed.
    """
    if platform.system() != "Linux":
        raise AllocatorDiagnosticsError("glibc diagnostics require Linux")
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        fdopen = libc.fdopen
        fdopen.argtypes = [ctypes.c_int, ctypes.c_char_p]
        fdopen.restype = ctypes.c_void_p
        malloc_info = libc.malloc_info
        malloc_info.argtypes = [ctypes.c_int, ctypes.c_void_p]
        malloc_info.restype = ctypes.c_int
        fclose = libc.fclose
        fclose.argtypes = [ctypes.c_void_p]
        fclose.restype = ctypes.c_int
        get_version = libc.gnu_get_libc_version
        get_version.argtypes = []
        get_version.restype = ctypes.c_char_p
    except (AttributeError, OSError) as exc:
        raise AllocatorDiagnosticsError("glibc malloc_info unavailable") from exc

    version = (get_version() or b"unknown").decode("ascii", errors="replace")

    with tempfile.TemporaryFile(mode="w+b") as tmp:
        fd = os.dup(tmp.fileno())
        stream = fdopen(fd, b"w")
        if not stream:
            os.close(fd)
            raise AllocatorDiagnosticsError("could not create glibc FILE stream")
        rc = -1
        close_rc = -1
        try:
            rc = malloc_info(0, stream)
        finally:
            # fclose flushes the stdio buffer, and closes ONLY the dup fd.
            close_rc = fclose(stream)
        if rc != 0 or close_rc != 0:
            raise AllocatorDiagnosticsError("glibc malloc_info serialization failed")
        tmp.seek(0)
        data = tmp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise AllocatorDiagnosticsError("glibc XML exceeded safe output limit")
        if not data:
            raise AllocatorDiagnosticsError("glibc XML was empty")
    return data, version


def capture_allocator() -> dict:
    """Capture a small diagnostic snapshot; must be invoked only while idle."""
    xml, glibc_version = _capture_glibc_xml()
    parsed = parse_malloc_info(xml)
    return {
        "pid": os.getpid(),
        "utc": datetime.now(timezone.utc).isoformat(),
        "source": "glibc_malloc_info",
        "glibc_version": glibc_version,
        "process_memory": process_smaps_rollup(),
        **parsed,
    }
