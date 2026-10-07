"""Unit tests for the backend-agnostic Director state machine."""

from __future__ import annotations

import unittest
import uuid

from workflowdirector.core import (
    DirectorEngine,
    JobState,
    MemoryObservation,
    PreparedStep,
    RunPhase,
    RunPlan,
    SubmissionTransportError,
    make_job_id,
)


async def no_sleep(_seconds):
    return None


class FakeAdapter:
    def __init__(self, scripted_states, *, lose_ack_for=None, mismatch_for=None):
        self.scripted_states = {
            job_id: list(states) for job_id, states in scripted_states.items()
        }
        self.lose_ack_for = set(lose_ack_for or [])
        self.mismatch_for = set(mismatch_for or [])
        self.submissions = []
        self.last_state = {}

    async def submit_prompt(self, *, prompt, prompt_id):
        self.submissions.append(prompt_id)
        if prompt_id in self.lose_ack_for:
            raise SubmissionTransportError("simulated connection loss")
        if prompt_id in self.mismatch_for:
            return str(uuid.uuid4())
        return prompt_id

    async def get_job_state(self, prompt_id):
        states = self.scripted_states.get(prompt_id)
        if states:
            state = states.pop(0)
            self.last_state[prompt_id] = state
            return state
        return self.last_state.get(prompt_id, JobState.UNKNOWN)


class FakeBoundary:
    def __init__(self, fail_on_step=None):
        self.calls = []
        self.fail_on_step = fail_on_step

    async def observe(self, *, step, job_id):
        self.calls.append((step.step_id, job_id))
        if step.step_id == self.fail_on_step:
            raise RuntimeError("simulated boundary failure")
        return [
            MemoryObservation.capture(
                f"POST_{step.step_id}",
                {"test": True, "step": step.step_id},
            )
        ]


def make_plan():
    return RunPlan(
        run_id=str(uuid.uuid4()),
        steps=(
            PreparedStep("A", "workflow-a", "Workflow A", {"1": {"class_type": "A"}}),
            PreparedStep("B", "workflow-b", "Workflow B", {"1": {"class_type": "B"}}),
        ),
    )


class DirectorEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_steps_are_strictly_sequential(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.PENDING, JobState.IN_PROGRESS, JobState.COMPLETED],
                b: [JobState.PENDING, JobState.COMPLETED],
            }
        )
        boundary = FakeBoundary()
        engine = DirectorEngine(
            adapter,
            boundary_observer=boundary,
            poll_interval_seconds=0,
            sleep=no_sleep,
        )

        record = await engine.run(plan)

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.submissions, [a, b])
        self.assertEqual([x[0] for x in boundary.calls], ["A", "B"])
        self.assertEqual(len(record.attempts[0].observations), 1)
        self.assertEqual(len(record.attempts[1].observations), 1)

        events = [(e.kind, e.step_id) for e in record.events]
        self.assertLess(
            events.index(("boundary_completed", "A")),
            events.index(("submission_started", "B")),
        )

    async def test_failed_first_job_stops_before_second_submission(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({a: [JobState.IN_PROGRESS, JobState.FAILED]})
        engine = DirectorEngine(adapter, poll_interval_seconds=0, sleep=no_sleep)

        record = await engine.run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "JOB_FAILED")
        self.assertEqual(adapter.submissions, [a])

    async def test_cancelled_job_stops_run(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({a: [JobState.CANCELLED]})
        engine = DirectorEngine(adapter, poll_interval_seconds=0, sleep=no_sleep)

        record = await engine.run(plan)

        self.assertEqual(record.phase, RunPhase.CANCELLED)
        self.assertEqual(adapter.submissions, [a])

    async def test_lost_submission_ack_is_recovered_by_preassigned_job_id(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.IN_PROGRESS, JobState.COMPLETED],
                b: [JobState.COMPLETED],
            },
            lose_ack_for={a},
        )
        engine = DirectorEngine(adapter, poll_interval_seconds=0, sleep=no_sleep)

        record = await engine.run(plan)

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.submissions, [a, b])
        self.assertTrue(any(e.kind == "submission_recovered" for e in record.events))

    async def test_unknown_lost_submission_is_never_blindly_retried(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({}, lose_ack_for={a})
        engine = DirectorEngine(adapter, poll_interval_seconds=0, sleep=no_sleep)

        record = await engine.run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "SUBMISSION_UNCERTAIN")
        self.assertEqual(adapter.submissions, [a])

    async def test_boundary_failure_prevents_next_workflow(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({a: [JobState.COMPLETED]})
        boundary = FakeBoundary(fail_on_step="A")
        engine = DirectorEngine(
            adapter,
            boundary_observer=boundary,
            poll_interval_seconds=0,
            sleep=no_sleep,
        )

        record = await engine.run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "BOUNDARY_FAILED")
        self.assertEqual(adapter.submissions, [a])

    async def test_job_id_is_stable_for_same_run_step_attempt(self):
        run_id = str(uuid.uuid4())
        first = make_job_id(run_id, "A", 1)
        second = make_job_id(run_id, "A", 1)
        retry = make_job_id(run_id, "A", 2)

        self.assertEqual(first, second)
        self.assertNotEqual(first, retry)


if __name__ == "__main__":
    unittest.main()
