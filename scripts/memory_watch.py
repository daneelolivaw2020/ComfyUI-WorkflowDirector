#!/usr/bin/env python3
"""Read-only external RAM/VRAM watcher for a running ComfyUI process.

Run from a separate Colab cell or shell. Never imports torch, accesses
Comfy's Python objects, modifies CUDA state, unloads models, or queues jobs.

    python scripts/memory_watch.py --duration 600 --interval 2
    python scripts/memory_watch.py --pid 1234 --duration 120

Produces JSONL samples with ISO UTC times to correlate with native Job IDs
and optional ProfilerX runs. This watcher measures the whole process and
device, not per-object allocations. Exit cleanly on Ctrl-C.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

DEFAULT_OUT = Path("/content/workflowdirector_memory_watch.jsonl")


def parse_kib_fields(raw: str) -> dict[str, int]:
    """Linux /proc/<pid>/smaps_rollup: convert selected kB fields to bytes."""
    wanted = {
        "Rss", "Pss", "Pss_Anon", "Pss_File", "Pss_Shmem",
        "Private_Clean", "Private_Dirty", "Shared_Clean",
        "Shared_Dirty", "Swap",
    }
    result = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        if name not in wanted:
            continue
        words = rest.strip().split()
        if not words:
            continue
        try:
            amount = int(words[0])
        except ValueError:
            continue
        # smaps uses kB, equal to KiB (1024 bytes).
        if len(words) > 1 and words[1] not in ("kB",):
            continue
        result[name.lower() + "_bytes"] = amount * 1024
    return result


def parse_nvidia_csv(stdout: str) -> list[dict[str, int | str]]:
    """Best-effort GPU-global used/total: NOT exclusive Comfy allocations."""
    result = []
    for line in stdout.splitlines():
        cells = [value.strip() for value in line.split(",")]
        if len(cells) < 3:
            continue
        try:
            idx = int(cells[0])
            used = int(cells[1].split()[0])
            total = int(cells[2].split()[0])
        except (ValueError, IndexError):
            continue
        result.append({
            "index": idx,
            "used_bytes": used * 1024 * 1024,
            "total_bytes": total * 1024 * 1024,
        })
    return result


def gpu_snapshot() -> list[dict[str, int | str]] | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode:
        return None
    return parse_nvidia_csv(completed.stdout)


def read_command(pid: int) -> list[str]:
    try:
        return [arg for arg in
                Path(f"/proc/{pid}/cmdline").read_bytes().decode(
                    "utf-8", errors="replace"
                ).split("\0") if arg]
    except (OSError, ValueError):
        return []


def is_comfy_process(pid: int, port: str) -> bool:
    cmd = read_command(pid)
    main = any(arg == "main.py" or arg.endswith("/ComfyUI/main.py")
               for arg in cmd)
    return bool(main and "--port" in cmd and port in cmd)


def find_comfy_pid(port: str) -> int:
    matches = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if is_comfy_process(pid, port):
            matches.append(pid)
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one ComfyUI main.py with --port {port}; "
            f"found {matches}. Pass --pid explicitly if needed."
        )
    return matches[0]


def read_proc_metrics(pid: int) -> dict:
    result = {}
    try:
        rollup = Path(f"/proc/{pid}/smaps_rollup").read_text()
        result.update(parse_kib_fields(rollup))
    except (OSError, UnicodeDecodeError) as exc:
        result["smaps_error"] = type(exc).__name__
    # Keep the process RSS measurement separate from total system RAM.
    try:
        statm = Path(f"/proc/{pid}/statm").read_text().split()
        result["process_rss_bytes_statm"] = int(statm[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, IndexError, ValueError):
        pass
    return result


def sample(pid: int) -> dict:
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "monotonic_s": round(time.monotonic(), 4),
        "comfy_pid": pid,
        "process": read_proc_metrics(pid),
        "gpu_global": gpu_snapshot(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--port", default="8188")
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if args.interval < 0.5 or args.duration <= 0:
        parser.error("--interval must be >= 0.5 and --duration > 0")
    pid = args.pid if args.pid is not None else find_comfy_pid(args.port)
    if not is_comfy_process(pid, args.port):
        raise RuntimeError(
            f"PID {pid} is not the expected ComfyUI main.py --port {args.port}. "
            "Not observing a possibly unrelated process."
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Monitoring Comfy PID={pid}, every {args.interval}s; "
          f"output={args.output}; press Ctrl-C to stop", flush=True)
    deadline = time.monotonic() + args.duration
    count = 0
    with args.output.open("a", encoding="utf-8") as file:
        try:
            while time.monotonic() < deadline:
                if not is_comfy_process(pid, args.port):
                    print("ComfyUI process disappeared or changed: STOP", file=sys.stderr)
                    return 2
                item = sample(pid)
                file.write(json.dumps(item, ensure_ascii=False) + "\n")
                file.flush()
                count += 1
                rss = item["process"].get("rss_bytes")
                mem = f"{rss / 2**30:.2f} GiB" if rss is not None else "unavailable"
                print(f"{item['utc']} pid={pid} RSS={mem} "
                      f"GPU={item['gpu_global']}", flush=True)
                time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))
        except KeyboardInterrupt:
            print("\nStopped on request, logs preserved.", flush=True)
    print(f"Saved {count} samples to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
