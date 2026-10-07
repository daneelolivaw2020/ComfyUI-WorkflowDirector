"""Unit tests for the non-destructive observation boundary."""

from __future__ import annotations

import unittest

from workflowdirector.boundary import ObservationBoundary
from workflowdirector.core import PreparedStep


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


class ObservationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_immediate_and_window_end_snapshots(self):
        fake_time = FakeTime()
        calls = []

        def snapshot():
            calls.append(fake_time.now)
            return {"t": fake_time.now}

        observer = ObservationBoundary(
            snapshot=snapshot,
            minimum_observation_seconds=3.0,
            sample_interval_seconds=1.0,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )

        step = PreparedStep("A", "wf-a", "A", {}, {})
        observations = await observer.observe(step=step, job_id="job-a")

        self.assertEqual(
            [item.label for item in observations],
            ["POST_IMMEDIATE", "POST_WINDOW_END"],
        )
        self.assertGreaterEqual(calls[-1] - calls[0], 3.0)

    async def test_zero_minimum_still_records_two_observations(self):
        fake_time = FakeTime()
        count = 0

        def snapshot():
            nonlocal count
            count += 1
            return {"count": count}

        observer = ObservationBoundary(
            snapshot=snapshot,
            minimum_observation_seconds=0,
            sample_interval_seconds=1,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )

        step = PreparedStep("A", "wf-a", "A", {}, {})
        observations = await observer.observe(step=step, job_id="job-a")

        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0].snapshot["count"], 1)
        self.assertEqual(observations[1].snapshot["count"], 2)


if __name__ == "__main__":
    unittest.main()
