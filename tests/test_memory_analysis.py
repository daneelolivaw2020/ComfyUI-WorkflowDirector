"""Tests for baseline-relative memory comparison."""

from __future__ import annotations

import unittest

from workflowdirector.core import (
    JobAttemptRecord,
    MemoryObservation,
    RunRecord,
)
from workflowdirector.memory_analysis import (
    compare_snapshots,
    summarize_run_memory,
)


def snap(*, rss, available, allocated, reserved, used, free, loaded):
    return {
        "process_rss_gib": rss,
        "system_ram": {
            "available_gib": available,
            "unavailable_gib": 12.0 - available,
        },
        "cuda": {
            "allocated_gib": allocated,
            "reserved_gib": reserved,
            "device_used_gib": used,
            "device_free_gib": free,
        },
        "diagnostics": {
            "comfy_loaded_model_entries": loaded,
        },
    }


class MemoryAnalysisTests(unittest.TestCase):
    def test_compare_keeps_metrics_separate(self):
        baseline = snap(
            rss=2.0,
            available=10.0,
            allocated=0.1,
            reserved=0.2,
            used=0.5,
            free=14.0,
            loaded=0,
        )
        current = snap(
            rss=4.0,
            available=8.0,
            allocated=1.1,
            reserved=2.2,
            used=3.5,
            free=11.0,
            loaded=2,
        )

        result = compare_snapshots(baseline, current)

        self.assertEqual(result["process_rss_gib"]["delta"], 2.0)
        self.assertEqual(result["system_available_gib"]["delta"], -2.0)
        self.assertEqual(result["cuda_allocated_gib"]["delta"], 1.0)
        self.assertEqual(result["cuda_reserved_gib"]["delta"], 2.0)
        self.assertEqual(result["cuda_device_used_gib"]["delta"], 3.0)
        self.assertEqual(result["loaded_model_entries"]["delta"], 2.0)

    def test_missing_cuda_is_reported_as_none_not_zero(self):
        baseline = {"process_rss_gib": 1.0, "cuda": None}
        current = {"process_rss_gib": 2.0, "cuda": None}

        result = compare_snapshots(baseline, current)

        self.assertIsNone(result["cuda_allocated_gib"]["baseline"])
        self.assertIsNone(result["cuda_allocated_gib"]["current"])
        self.assertIsNone(result["cuda_allocated_gib"]["delta"])

    def test_run_summary_compares_each_observation_to_same_baseline(self):
        record = RunRecord(run_id="run")
        record.observations.append(
            MemoryObservation.capture(
                "BASELINE",
                snap(
                    rss=2.0,
                    available=10.0,
                    allocated=0.1,
                    reserved=0.2,
                    used=0.5,
                    free=14.0,
                    loaded=0,
                ),
            )
        )
        attempt = JobAttemptRecord(
            step_id="A",
            workflow_id="wf-a",
            attempt=1,
            job_id="job-a",
        )
        attempt.observations.extend(
            [
                MemoryObservation.capture(
                    "POST_IMMEDIATE",
                    snap(
                        rss=5.0,
                        available=7.0,
                        allocated=5.0,
                        reserved=6.0,
                        used=7.0,
                        free=7.5,
                        loaded=3,
                    ),
                ),
                MemoryObservation.capture(
                    "POST_WINDOW_END",
                    snap(
                        rss=3.0,
                        available=9.0,
                        allocated=1.0,
                        reserved=2.0,
                        used=2.5,
                        free=12.0,
                        loaded=1,
                    ),
                ),
            ]
        )
        record.attempts.append(attempt)

        summary = summarize_run_memory(record)

        self.assertTrue(summary["baseline_found"])
        observations = summary["steps"][0]["observations"]
        self.assertEqual(observations[0]["label"], "POST_IMMEDIATE")
        self.assertEqual(observations[1]["label"], "POST_WINDOW_END")
        self.assertEqual(
            observations[1]["metrics"]["process_rss_gib"]["delta"],
            1.0,
        )

    def test_summary_without_baseline_refuses_release_interpretation(self):
        summary = summarize_run_memory(RunRecord(run_id="run"))

        self.assertFalse(summary["baseline_found"])
        self.assertEqual(summary["steps"], [])


if __name__ == "__main__":
    unittest.main()
