"""Unit tests for the backend-agnostic Director state machine."""

from __future__ import annotations

import json
import unittest
import uuid

from workflowdirector.core import (
    AdapterTransportError,
    DirectorEngine,
    JobState,
    MemoryObservation,
    PreparedStep,
    RunPhase,
    RunPlan,
    SubmissionTransportError,
    make_job_id,
)


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.now += max(seconds, 0.001)


class FakeAdapter:
    def __init__(
        self,
        scripted_states,
        *,
        lose_ack_for=None,
        mismatch_for=None,
        transient_status_errors=None,
        active_job_sequences=None,
    ):
        self.scripted_states = {
            job_id: list(states) for job_id, states in scripted_states.items()
        }
        self.lose_ack_for = set(lose_ack_for or [])
        self.mismatch_for = set(mismatch_for or [])
        self.submissions = []
        self.submitted_clients = []
        self.last_state = {}
        self.transient_status_errors = dict(transient_status_errors or {})
        self.active_job_sequences = [
            set(items) for items in (active_job_sequences or [])
        ]

    async def submit_prompt(self, *, prompt, workflow, prompt_id, client_id):
        self.submissions.append(prompt_id)
        self.submitted_clients.append(client_id)
        if prompt_id in self.lose_ack_for:
            raise SubmissionTransportError("simulated connection loss")
        if prompt_id in self.mismatch_for:
            return str(uuid.uuid4())
        return prompt_id

    async def get_active_job_ids(self):
        if self.active_job_sequences:
            return self.active_job_sequences.pop(0)
        return set()

    async def get_job_state(self, prompt_id):
        remaining_errors = self.transient_status_errors.get(prompt_id, 0)
        if remaining_errors > 0:
            self.transient_status_errors[prompt_id] = remaining_errors - 1
            raise AdapterTransportError("simulated temporary disconnect")

        states = self.scripted_states.get(prompt_id)
        if states:
            state = states.pop(0)
            self.last_state[prompt_id] = state
            return state
        return self.last_state.get(prompt_id, JobState.UNKNOWN)


class FakeRunObserver:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def before_run(self, *, plan):
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated baseline failure")
        return [
            MemoryObservation.capture(
                "BASELINE",
                {"test": True, "run_id": plan.run_id},
            )
        ]


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
            PreparedStep(
                "A",
                "workflow-a",
                "Workflow A",
                {"1": {"class_type": "A"}},
                {"id": "workflow-a", "nodes": []},
            ),
            PreparedStep(
                "B",
                "workflow-b",
                "Workflow B",
                {"1": {"class_type": "B"}},
                {"id": "workflow-b", "nodes": []},
            ),
        ),
    )


def make_engine(
    adapter,
    *,
    boundary=None,
    run_observer=None,
    job_timeout=10.0,
    recovery_timeout=1.0,
):
    fake_time = FakeTime()
    return DirectorEngine(
        adapter,
        boundary_observer=boundary,
        run_observer=run_observer,
        poll_interval_seconds=0.1,
        job_timeout_seconds=job_timeout,
        submission_recovery_timeout_seconds=recovery_timeout,
        sleep=fake_time.sleep,
        clock=fake_time.clock,
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
        engine = make_engine(adapter, boundary=boundary)

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
        record = await make_engine(adapter).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "JOB_FAILED")
        self.assertEqual(adapter.submissions, [a])

    async def test_cancelled_job_stops_run(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({a: [JobState.CANCELLED]})
        record = await make_engine(adapter).run(plan)

        self.assertEqual(record.phase, RunPhase.CANCELLED)
        self.assertEqual(record.failure_code, "JOB_CANCELLED")
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

        record = await make_engine(adapter).run(plan)

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.submissions, [a, b])
        self.assertTrue(any(e.kind == "submission_recovered" for e in record.events))

    async def test_lost_ack_tolerates_temporary_unknown_visibility(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [
                    JobState.UNKNOWN,
                    JobState.UNKNOWN,
                    JobState.IN_PROGRESS,
                    JobState.COMPLETED,
                ],
                b: [JobState.COMPLETED],
            },
            lose_ack_for={a},
        )

        record = await make_engine(
            adapter,
            recovery_timeout=0.3,
        ).run(plan)

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.submissions, [a, b])

    async def test_unknown_lost_submission_is_never_blindly_retried(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({}, lose_ack_for={a})

        record = await make_engine(
            adapter,
            recovery_timeout=0.3,
        ).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "SUBMISSION_UNCERTAIN")
        self.assertEqual(adapter.submissions, [a])

    async def test_temporary_status_disconnect_does_not_submit_duplicate(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.IN_PROGRESS, JobState.COMPLETED],
                b: [JobState.COMPLETED],
            },
            transient_status_errors={a: 2},
        )

        record = await make_engine(adapter).run(plan)

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.submissions, [a, b])
        self.assertTrue(
            any(e.kind == "job_status_transport_error" for e in record.events)
        )

    async def test_foreign_active_job_blocks_first_submission(self):
        plan = make_plan()
        adapter = FakeAdapter(
            {},
            active_job_sequences=[{"foreign-job"}],
        )

        record = await make_engine(adapter).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "QUEUE_NOT_EXCLUSIVE")
        self.assertEqual(adapter.submissions, [])

    async def test_foreign_job_during_execution_stops_run(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.PENDING, JobState.IN_PROGRESS],
            },
            active_job_sequences=[
                set(),
                set(),
                {a},
                {a, "foreign-job"},
            ],
        )

        record = await make_engine(adapter).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "QUEUE_INTERFERENCE")
        self.assertEqual(adapter.submissions, [a])

    async def test_foreign_job_between_steps_blocks_second_submission(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter(
            {a: [JobState.COMPLETED]},
            active_job_sequences=[set(), set(), {"foreign-job"}],
        )
        boundary = FakeBoundary()

        record = await make_engine(adapter, boundary=boundary).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "QUEUE_NOT_EXCLUSIVE")
        self.assertEqual(adapter.submissions, [a])

    async def test_run_baseline_is_captured_before_first_submission(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.COMPLETED],
                b: [JobState.COMPLETED],
            }
        )
        observer = FakeRunObserver()

        record = await make_engine(
            adapter,
            run_observer=observer,
        ).run(plan)

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(
            [item.label for item in record.observations],
            ["BASELINE"],
        )

        kinds = [event.kind for event in record.events]
        self.assertLess(
            kinds.index("run_observer_completed"),
            kinds.index("submission_started"),
        )

    async def test_run_observer_failure_prevents_any_submission(self):
        plan = make_plan()
        adapter = FakeAdapter({})
        observer = FakeRunObserver(fail=True)

        record = await make_engine(
            adapter,
            run_observer=observer,
        ).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "RUN_OBSERVER_FAILED")
        self.assertEqual(adapter.submissions, [])

    async def test_boundary_failure_prevents_next_workflow(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({a: [JobState.COMPLETED]})
        boundary = FakeBoundary(fail_on_step="A")

        record = await make_engine(adapter, boundary=boundary).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "BOUNDARY_FAILED")
        self.assertEqual(adapter.submissions, [a])

    async def test_client_id_is_runtime_routing_not_runplan_state(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.COMPLETED],
                b: [JobState.COMPLETED],
            }
        )

        record = await make_engine(adapter).run(
            plan,
            client_id="browser-session",
        )

        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(
            adapter.submitted_clients,
            ["browser-session", "browser-session"],
        )
        self.assertFalse(hasattr(plan, "client_id"))

    async def test_prepared_prompt_and_workflow_are_real_snapshots(self):
        prompt_source = {"1": {"class_type": "Original", "inputs": {"value": 1}}}
        workflow_source = {"id": "workflow-a", "nodes": [{"id": 1}]}
        step = PreparedStep(
            "A",
            "workflow-a",
            "Workflow A",
            prompt_source,
            workflow_source,
        )

        prompt_source["1"]["class_type"] = "Mutated"
        workflow_source["nodes"][0]["id"] = 999

        prompt_read = step.prompt
        workflow_read = step.workflow
        prompt_read["1"]["class_type"] = "Also Mutated"
        workflow_read["nodes"][0]["id"] = 888

        self.assertEqual(step.prompt["1"]["class_type"], "Original")
        self.assertEqual(step.workflow["nodes"][0]["id"], 1)

    async def test_run_record_is_json_serializable(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        b = make_job_id(plan.run_id, "B", 1)
        adapter = FakeAdapter(
            {
                a: [JobState.COMPLETED],
                b: [JobState.COMPLETED],
            }
        )
        boundary = FakeBoundary()

        record = await make_engine(adapter, boundary=boundary).run(plan)
        encoded = json.dumps(record.to_dict())

        self.assertIn(plan.run_id, encoded)
        self.assertIn("completed", encoded)

    async def test_memory_observation_deep_copies_nested_snapshot(self):
        source = {"cuda": {"allocated_gib": 1.0}}
        observation = MemoryObservation.capture("X", source)
        source["cuda"]["allocated_gib"] = 99.0

        self.assertEqual(observation.snapshot["cuda"]["allocated_gib"], 1.0)

    async def test_job_timeout_uses_monotonic_time_not_poll_count(self):
        plan = make_plan()
        a = make_job_id(plan.run_id, "A", 1)
        adapter = FakeAdapter({a: [JobState.IN_PROGRESS]})

        record = await make_engine(
            adapter,
            job_timeout=0.3,
        ).run(plan)

        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "JOB_STATUS_TIMEOUT")
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
