"""Unit tests for non-destructive run and boundary observations."""

from __future__ import annotations

import unittest
import uuid

from workflowdirector.boundary import (
    BoundaryInterferenceError,
    ObservationBoundary,
    SnapshotRunObserver,
)
from workflowdirector.core import PreparedStep, RunPlan


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def make_plan():
    return RunPlan(
        run_id=str(uuid.uuid4()),
        steps=(PreparedStep("A", "wf-a", "A", {}, {}),),
    )


class SnapshotRunObserverTests(unittest.IsolatedAsyncioTestCase):
    async def test_warmup_is_discarded_and_second_snapshot_is_baseline(self):
        count = 0

        def snapshot():
            nonlocal count
            count += 1
            return {"count": count}

        observer = SnapshotRunObserver(
            snapshot=snapshot,
            warm_up=True,
        )

        observations = await observer.before_run(plan=make_plan())

        self.assertEqual(count, 2)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].label, "BASELINE")
        self.assertEqual(observations[0].snapshot["count"], 2)

    async def test_baseline_interference_is_rejected(self):
        calls = 0

        async def active_jobs():
            nonlocal calls
            calls += 1
            return set() if calls < 3 else {"foreign-job"}

        observer = SnapshotRunObserver(
            snapshot=lambda: {"ok": True},
            warm_up=True,
            active_jobs=active_jobs,
        )

        with self.assertRaises(BoundaryInterferenceError):
            await observer.before_run(plan=make_plan())

    async def test_warmup_can_be_disabled(self):
        count = 0

        def snapshot():
            nonlocal count
            count += 1
            return {"count": count}

        observer = SnapshotRunObserver(
            snapshot=snapshot,
            warm_up=False,
        )

        observations = await observer.before_run(plan=make_plan())

        self.assertEqual(count, 1)
        self.assertEqual(observations[0].snapshot["count"], 1)


class ObservationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_immediate_and_window_end_snapshots(self):
        fake_time = FakeTime()
        calls = []

        def snapshot():
            calls.append(fake_time.now)
            return {"t": fake_time.now}

        observer = ObservationBoundary(
            snapshot=snapshot,
            observation_window_seconds=3.0,
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

    async def test_zero_window_still_records_two_observations(self):
        fake_time = FakeTime()
        count = 0

        def snapshot():
            nonlocal count
            count += 1
            return {"count": count}

        observer = ObservationBoundary(
            snapshot=snapshot,
            observation_window_seconds=0,
            sample_interval_seconds=1,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )

        step = PreparedStep("A", "wf-a", "A", {}, {})
        observations = await observer.observe(step=step, job_id="job-a")

        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0].snapshot["count"], 1)
        self.assertEqual(observations[1].snapshot["count"], 2)

    async def test_foreign_job_at_boundary_start_invalidates_observation(self):
        async def active_jobs():
            return {"foreign-job"}

        observer = ObservationBoundary(
            snapshot=lambda: {"ok": True},
            observation_window_seconds=1,
            active_jobs=active_jobs,
        )

        with self.assertRaises(BoundaryInterferenceError):
            await observer.observe(
                step=PreparedStep("A", "wf-a", "A", {}, {}),
                job_id="job-a",
            )

    async def test_foreign_job_appearing_during_window_invalidates_observation(self):
        fake_time = FakeTime()
        calls = 0

        async def active_jobs():
            nonlocal calls
            calls += 1
            return set() if calls < 3 else {"foreign-job"}

        observer = ObservationBoundary(
            snapshot=lambda: {"t": fake_time.now},
            observation_window_seconds=3,
            sample_interval_seconds=1,
            active_jobs=active_jobs,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )

        with self.assertRaises(BoundaryInterferenceError):
            await observer.observe(
                step=PreparedStep("A", "wf-a", "A", {}, {}),
                job_id="job-a",
            )


if __name__ == "__main__":
    unittest.main()
