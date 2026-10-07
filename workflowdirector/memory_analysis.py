"""Pure helpers for comparing WorkflowDirector memory observations.

No conclusion such as "model unloaded" is inferred from one metric. The output
keeps allocator, process, system and device-global measurements separate.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .core import MemoryObservation, RunRecord


_METRICS = {
    "process_rss_gib": ("process_rss_gib",),
    "system_available_gib": ("system_ram", "available_gib"),
    "system_unavailable_gib": ("system_ram", "unavailable_gib"),
    "cuda_allocated_gib": ("cuda", "allocated_gib"),
    "cuda_reserved_gib": ("cuda", "reserved_gib"),
    "cuda_device_used_gib": ("cuda", "device_used_gib"),
    "cuda_device_free_gib": ("cuda", "device_free_gib"),
    "loaded_model_entries": ("diagnostics", "comfy_loaded_model_entries"),
}


def _read_number(snapshot: Mapping[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = snapshot
    for part in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def compare_snapshots(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, dict[str, float | None]]:
    """Compare current memory metrics to one baseline snapshot."""

    result: dict[str, dict[str, float | None]] = {}
    for name, path in _METRICS.items():
        before = _read_number(baseline, path)
        after = _read_number(current, path)
        delta = None
        if before is not None and after is not None:
            delta = round(after - before, 4)

        result[name] = {
            "baseline": before,
            "current": after,
            "delta": delta,
        }
    return result


def summarize_run_memory(record: RunRecord) -> dict[str, Any]:
    """Return baseline-relative comparisons for every boundary observation."""

    baseline: MemoryObservation | None = None
    for observation in record.observations:
        if observation.label == "BASELINE":
            baseline = observation
            break

    if baseline is None:
        return {
            "baseline_found": False,
            "baseline": None,
            "steps": [],
            "interpretation": (
                "No BASELINE observation is available. No release conclusion "
                "can be drawn from this run."
            ),
        }

    steps = []
    for attempt in record.attempts:
        comparisons = []
        for observation in attempt.observations:
            comparisons.append(
                {
                    "label": observation.label,
                    "captured_at": observation.captured_at,
                    "metrics": compare_snapshots(
                        baseline.snapshot,
                        observation.snapshot,
                    ),
                }
            )

        steps.append(
            {
                "step_id": attempt.step_id,
                "workflow_id": attempt.workflow_id,
                "job_id": attempt.job_id,
                "observations": comparisons,
            }
        )

    return {
        "baseline_found": True,
        "baseline": {
            "label": baseline.label,
            "captured_at": baseline.captured_at,
            "snapshot": baseline.snapshot,
        },
        "steps": steps,
        "interpretation": (
            "Deltas are descriptive only. Lower torch allocated/reserved memory "
            "does not by itself prove that a model object was destroyed; "
            "device-global VRAM, process RSS, system RAM and loaded-model "
            "diagnostics must be considered separately."
        ),
    }
