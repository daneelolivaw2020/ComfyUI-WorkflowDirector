"""Read Linux process PSS without influencing CUDA or Comfy's model state.

On Colab, /proc/self/smaps_rollup distinguishes anonymous PSS (usually
allocator/python/native-memory pages) from file-backed PSS (which may include
mmap). Values are approximate MiB/GiB page accounting, not ownership proof.
This module has no third-party dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path


# Kernel smaps_rollup reports KiB. Conversion to GiB divides by 1024**2.
_FIELDS = {
    "Rss": "rss_gib",
    "Pss": "pss_gib",
    "Pss_Anon": "pss_anon_gib",
    "Pss_File": "pss_file_gib",
    "Pss_Shmem": "pss_shmem_gib",
    "Anonymous": "anonymous_gib",
    "Private_Dirty": "private_dirty_gib",
    "Private_Clean": "private_clean_gib",
    "Shared_Clean": "shared_clean_gib",
    "Swap": "swap_gib",
}


def parse_smaps_rollup(content: str) -> dict[str, float]:
    """Safely parse selected fields from one /proc/PID/smaps_rollup."""
    result: dict[str, float] = {}
    for line in content.splitlines():
        key, separator, rest = line.partition(":")
        if not separator or key not in _FIELDS:
            continue
        parts = rest.strip().split()
        if len(parts) < 2 or parts[1] != "kB":
            continue
        try:
            kib = int(parts[0])
        except ValueError:
            continue
        if kib < 0:
            continue
        result[_FIELDS[key]] = round(kib / (1024**2), 4)
    return result


def process_smaps_rollup(pid: int | None = None) -> dict[str, float]:
    """Best-effort Linux diagnostics, returning {} when unsupported."""
    if pid is None:
        pid = os.getpid()
    if not isinstance(pid, int) or pid <= 0:
        return {}
    try:
        content = Path(f"/proc/{pid}/smaps_rollup").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    return parse_smaps_rollup(content)
