#!/usr/bin/env python3
"""Read-only preflight + small native A→B Context acceptance runs in Colab.

Uses the *real* ComfyUI /workflowdirector/runs endpoint. Does not load GGUF,
install packages, restart Comfy, call /free, or modify Comfy's cache policy.

Usage:
  python scripts/acceptance_probe.py --case preflight
  python scripts/acceptance_probe.py --case string
  python scripts/acceptance_probe.py --case image
  python scripts/acceptance_probe.py --case latent
  python scripts/acceptance_probe.py --case failure
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8188"
REPORT = Path("/content/workflowdirector_acceptance_report.json")
NODE_TYPES = (
    "WorkflowDirectorContextPutString",
    "WorkflowDirectorContextGetString",
    "WorkflowDirectorContextPutImage",
    "WorkflowDirectorContextGetImage",
    "WorkflowDirectorContextPutLatent",
    "WorkflowDirectorContextGetLatent",
    "WorkflowDirectorTestMarker",
    "EmptyImage", "EmptyLatentImage", "SaveImage", "SaveLatent",
)


def api(path, *, method="GET", data=None, timeout=15):
    payload = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        BASE + path, data=payload, method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        body = err.read(1200).decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path}: HTTP {err.code}: {body}") from err


def active_ids():
    state = api("/api/jobs?status=pending,in_progress")
    if not isinstance(state, dict):
        raise RuntimeError("Invalid native Jobs API shape")
    jobs = state.get("jobs")
    if not isinstance(jobs, list):
        raise RuntimeError("Native Jobs API does not expose a jobs array")
    return [job.get("id") for job in jobs]


def preflight():
    health = api("/workflowdirector/health")
    stats = api("/system_stats")
    object_info = api("/object_info", timeout=30)
    if health.get("comfyui_version") != "0.39.0":
        raise RuntimeError(
            "Wrong Comfy version: " + str(health.get("comfyui_version")) +
            " (expected 0.39.0)"
        )
    info = health.get("director_service") or {}
    if not info.get("ready"):
        raise RuntimeError("Director service is not ready: " + str(info))
    if info.get("active_run_id"):
        raise RuntimeError("Director run already active: " + info["active_run_id"])
    in_progress = active_ids()
    if in_progress:
        raise RuntimeError("Other native Comfy jobs are active: " + repr(in_progress))
    missing = [name for name in NODE_TYPES if name not in object_info]
    if missing:
        raise RuntimeError("Required Comfy nodes missing: " + repr(missing))
    pid = find_main_pid()
    print("PASS — Preflight: Comfy 0.39.0, Director ready, all nodes registered")
    print("Backend:", health.get("workflowdirector_version"))
    print("GPU devices:", len(stats.get("devices", [])))
    if pid:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().decode(
            "utf-8", errors="replace"
        ).split("\0")
        if "--cache-none" not in args:
            raise RuntimeError(
                "This test requires the previously validated --cache-none; "
                "restart with your exact known-working launch flags."
            )
        print("PASS — --cache-none present in live Comfy command (PID", pid, ")")
    else:
        raise RuntimeError(
            "Cannot verify the live Comfy command. Check --cache-none manually."
        )
    return health


def find_main_pid():
    matches = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / "cmdline").read_bytes().decode(
                "utf-8", errors="replace"
            ).split("\0")
        except (OSError, PermissionError):
            continue
        if any(arg.endswith("/ComfyUI/main.py") or arg == "main.py"
               for arg in args) and "--port" in args and "8188" in args:
            matches.append(int(entry.name))
    if len(matches) != 1:
        return None
    return matches[0]


def step(name, cls, prompt):
    return {
        "step_id": name,
        "workflow_id": str(uuid.uuid4()),
        "name": f"Context acceptance {name}: {cls}",
        "prompt": prompt,
        "workflow": {"id": str(uuid.uuid4()), "nodes": []},
    }


def plans(case):
    run = uuid.uuid4().hex[:12]
    if case == "string":
        sentinel = "WD_CONTEXT_SENTINEL_" + run
        a = {"1": {"class_type": "WorkflowDirectorContextPutString",
                   "inputs": {"key": "accept.text", "value": sentinel}}}
        b = {
            "1": {"class_type": "WorkflowDirectorContextGetString",
                  "inputs": {"key": "accept.text"}},
            "2": {"class_type": "WorkflowDirectorTestMarker",
                  "inputs": {"label": ["1", 0]}},
        }
        return [step("A", "PutString", a), step("B", "GetString", b)], (
            "accept.text", "STRING", sentinel
        )

    if case == "image":
        a = {
            "1": {"class_type": "EmptyImage",
                  "inputs": {"width": 96, "height": 64, "batch_size": 1,
                             "color": 0xE23C65}},
            "2": {"class_type": "WorkflowDirectorContextPutImage",
                  "inputs": {"key": "accept.image", "value": ["1", 0]}},
        }
        b = {
            "1": {"class_type": "WorkflowDirectorContextGetImage",
                  "inputs": {"key": "accept.image"}},
            "2": {"class_type": "SaveImage",
                  "inputs": {"images": ["1", 0],
                             "filename_prefix": f"WD_Acceptance_IMAGE_{run}"}},
        }
        return [step("A", "PutImage", a), step("B", "GetImage", b)], (
            "accept.image", "IMAGE", f"WD_Acceptance_IMAGE_{run}"
        )

    if case == "latent":
        a = {
            "1": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": 64, "height": 64, "batch_size": 1}},
            "2": {"class_type": "WorkflowDirectorContextPutLatent",
                  "inputs": {"key": "accept.latent", "value": ["1", 0]}},
        }
        b = {
            "1": {"class_type": "WorkflowDirectorContextGetLatent",
                  "inputs": {"key": "accept.latent"}},
            "2": {"class_type": "SaveLatent",
                  "inputs": {"samples": ["1", 0],
                             "filename_prefix": f"WD_Acceptance_LATENT_{run}"}},
        }
        return [step("A", "PutLatent", a), step("B", "GetLatent", b)], (
            "accept.latent", "LATENT", f"WD_Acceptance_LATENT_{run}"
        )

    if case == "failure":
        a = {
            "1": {"class_type": "WorkflowDirectorContextGetString",
                  "inputs": {"key": "this.key.does.not.exist"}},
            "2": {"class_type": "WorkflowDirectorTestMarker",
                  "inputs": {"label": ["1", 0]}},
        }
        b = {"1": {"class_type": "WorkflowDirectorContextPutString",
                   "inputs": {"key": "should.not.appear", "value": "ERROR"}}}
        return [step("A", "ExpectedFailure", a),
                step("B", "MustNotRun", b)], (None, None, None)
    raise ValueError(case)


def history_evidence(job_id, expected_fragment):
    try:
        h = api("/history/" + job_id, timeout=10)
    except Exception as exc:
        return {"available": False, "detail": str(exc)}
    body = json.dumps(h, ensure_ascii=False)
    return {
        "available": bool(h),
        "expected_fragment_found": expected_fragment in body,
        "job_present": job_id in h,
    }


def last_step_rss(status):
    """Last step's final RSS, or None if the step has no memory observations."""
    steps = (status.get("memory_summary") or {}).get("steps") or []
    if not steps:
        return None
    observations = steps[-1].get("observations") or []
    if not observations:
        return None
    return observations[-1].get("metrics", {}).get("process_rss_gib", {}).get("current")


def run_case(case, *, max_seconds=120):
    # The run service exclusively owns jobs; never submit around an active run.
    preflight()
    steps, (key, kind, expected_fragment) = plans(case)
    rid = str(uuid.uuid4())
    print(f"\nRunning {case} — {rid}")
    response = api("/workflowdirector/runs", method="POST", data={
        "run_id": rid, "steps": steps,
    }, timeout=25)
    if response.get("run_id") != rid:
        raise RuntimeError("Director Run ID acknowledgement mismatch")
    deadline = time.monotonic() + max_seconds
    record = {}
    while time.monotonic() < deadline:
        status = api("/workflowdirector/runs/" + rid)
        record = status.get("record") or {}
        phase = record.get("phase")
        if phase in ("completed", "failed", "cancelled"):
            break
        time.sleep(1)
    else:
        raise RuntimeError(
            "Run did not report a terminal state. Do NOT submit another job; "
            f"inspect /workflowdirector/runs/{rid}"
        )
    phase = record.get("phase")
    attempts = record.get("attempts") or []
    manifest = record.get("context_manifest") or {}
    expected_failed = case == "failure"
    good_phase = phase == ("failed" if expected_failed else "completed")
    good_attempts = (
        len(attempts) == (1 if expected_failed else 2)
        and (len(attempts) == 1 or attempts[0]["job_id"] != attempts[1]["job_id"])
    )
    context_ok = (
        not manifest if expected_failed
        else manifest.get(key, {}).get("type") == kind
        and manifest[key].get("bytes", 0) > 0
    )
    evidence = None
    if not expected_failed and len(attempts) > 1:
        evidence = history_evidence(attempts[1]["job_id"], expected_fragment)

    data = {
        "case": case, "run_id": rid, "phase": phase,
        "failure_code": record.get("failure_code"),
        "attempts": [{
            "step_id": a.get("step_id"),
            "job_id": a.get("job_id"),
            "state": a.get("state"),
        } for a in attempts],
        "context_manifest": manifest,
        "history_evidence": evidence,
        "success": good_phase and good_attempts and context_ok,
        "end_rss_gib": last_step_rss(status),
    }
    previous = []
    if REPORT.exists():
        try:
            previous = json.loads(REPORT.read_text())
        except (ValueError, OSError):
            previous = []
    if not isinstance(previous, list):
        previous = []
    previous.append(data)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(previous, ensure_ascii=False, indent=2))

    print(json.dumps(data, ensure_ascii=False, indent=2))
    if not data["success"]:
        raise RuntimeError(
            f"Acceptance {case} failed. Stop here and inspect the Comfy log."
        )
    print(f"PASS — {case.upper()} A→B; report: {REPORT}")
    if evidence and not evidence["expected_fragment_found"]:
        print(
            "NOTE: native /history evidence was incomplete. Check B output "
            "file/log manually before final sign-off."
        )
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", choices=("preflight", "string", "image", "latent", "failure"),
        required=True
    )
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        if args.case == "preflight":
            preflight()
        else:
            run_case(args.case, max_seconds=args.timeout)
    except Exception as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
