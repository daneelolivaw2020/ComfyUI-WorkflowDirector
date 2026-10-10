"""Backend-independent transactional Context tests (no GPU or Torch needed)."""

from __future__ import annotations

import copy
import unittest
import uuid

from workflowdirector.context import (
    ContextError,
    ContextNotFound,
    ContextRegistry,
)
from workflowdirector.run_api import RunRequestError, parse_run_request
from workflowdirector.core import (
    DirectorEngine,
    DirectorRunService,
    JobState,
    PreparedStep,
    RunPhase,
    RunPlan,
)


class FakeCodec:
    def estimate_size(self, kind, value):
        if kind == "STRING":
            if not isinstance(value, str):
                raise ContextError("not a STRING")
            return len(value.encode("utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("data"), bytearray):
            raise ContextError("models are not allowed")
        return len(value["data"])

    def copy_in(self, kind, value):
        size = self.estimate_size(kind, value)
        return copy.deepcopy(value), size

    def copy_out(self, kind, value):
        return copy.deepcopy(value)


def registry(max_entry=128, max_total=256):
    return ContextRegistry(
        FakeCodec(),
        max_entry_bytes=max_entry,
        max_total_bytes=max_total,
    )


class ContextRegistryTests(unittest.TestCase):
    def test_optional_get_reports_missing_outside_a_director_run(self):
        store = registry()
        self.assertEqual(store.try_read_any("manual-job", "render1"), (False, None))

    def test_optional_get_reports_missing_for_b_only_and_staged_values(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "B", "job-B")
        self.assertEqual(store.try_read_any("job-B", "render1"), (False, None))
        store.stage("job-B", "render1", "STRING", "not-committed")
        self.assertEqual(store.try_read_any("job-B", "render1"), (False, None))
        store.commit_step("job-B")
        store.begin_step("run", "C", "job-C")
        self.assertEqual(
            store.try_read_any("job-C", "render1"), (True, "not-committed")
        )
        store.end_run("run")

    def test_optional_get_clones_committed_values(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "render1", "IMAGE", {"data": bytearray(b"abc")})
        store.commit_step("job-A")
        store.begin_step("run", "B", "job-B")
        found, value = store.try_read_any("job-B", "render1")
        self.assertTrue(found)
        value["data"][0] = ord("X")
        self.assertEqual(
            store.try_read_any("job-B", "render1")[1]["data"],
            bytearray(b"abc"),
        )
        store.end_run("run")

    def test_optional_get_refuses_foreign_or_abandoned_jobs(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        with self.assertRaisesRegex(ContextError, "not the active"):
            store.try_read_any("unrelated-job", "render1")
        with self.assertRaises(ContextError):
            store.try_read_any("job-A", " invalid ")
        store.end_run("run")
        with self.assertRaisesRegex(ContextError, "ended or aborted"):
            store.try_read_any("job-A", "render1")

    def test_uncommitted_value_is_not_visible_and_commit_makes_it_visible(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "artist.image", "IMAGE", {"data": bytearray(b"abc")})
        with self.assertRaises(ContextNotFound):
            store.read("job-A", "artist.image", "IMAGE")
        self.assertEqual(store.manifest(), {})
        self.assertEqual(store.commit_step("job-A"), ("artist.image",))
        self.assertEqual(
            store.manifest(), {"artist.image": {"type": "IMAGE", "bytes": 3}}
        )
        store.begin_step("run", "B", "job-B")
        output = store.read("job-B", "artist.image", "IMAGE")
        output["data"][0] = ord("X")
        self.assertEqual(
            store.read("job-B", "artist.image", "IMAGE")["data"],
            bytearray(b"abc"),
        )
        store.commit_step("job-B")
        store.end_run("run")

    def test_discard_keeps_prior_committed_values(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "a", "STRING", "committed")
        store.commit_step("job-A")
        store.begin_step("run", "B", "job-B")
        store.stage("job-B", "a", "STRING", "wrong")
        store.stage("job-B", "b", "STRING", "never published")
        store.discard_step("job-B")
        store.begin_step("run", "C", "job-C")
        self.assertEqual(store.read("job-C", "a", "STRING"), "committed")
        with self.assertRaises(ContextNotFound):
            store.read("job-C", "b", "STRING")
        store.end_run("run")

    def test_two_writers_same_key_in_one_step_are_rejected(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "image", "STRING", "first")
        with self.assertRaisesRegex(ContextError, "multiple writers"):
            store.stage("job-A", "image", "STRING", "second")
        store.end_run("run")

    def test_model_object_type_is_forbidden(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        with self.assertRaisesRegex(ContextError, "forbidden"):
            store.stage("job-A", "model", "MODEL", object())
        with self.assertRaisesRegex(ContextError, "models are not allowed"):
            store.stage("job-A", "image", "IMAGE", object())
        store.end_run("run")

    def test_unauthorized_prompt_cannot_read_or_write(self):
        store = registry()
        with self.assertRaises(ContextError):
            store.read("manual-queue", "x", "STRING")
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        with self.assertRaisesRegex(ContextError, "not the active"):
            store.stage("manual-queue", "x", "STRING", "nope")
        with self.assertRaisesRegex(ContextError, "not the active"):
            store.read("manual-queue", "x", "STRING")
        store.end_run("run")

    def test_size_budget_is_enforced_without_partial_publication(self):
        store = registry(max_entry=12, max_total=12)
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "a", "STRING", "123456")
        with self.assertRaisesRegex(ContextError, "CPU RAM budget"):
            store.stage("job-A", "b", "STRING", "1234567")
        with self.assertRaisesRegex(ContextError, "per-entry"):
            store.stage("job-A", "c", "STRING", "z" * 13)
        self.assertEqual(store.manifest(), {})
        store.discard_step("job-A")
        self.assertEqual(store.manifest(), {})
        store.end_run("run")

    def test_replacing_entries_accounts_for_coexisting_versions(self):
        store = registry(max_entry=12, max_total=12)
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "x", "STRING", "123456")
        store.stage("job-A", "y", "STRING", "789012")
        store.commit_step("job-A")
        store.begin_step("run", "B", "job-B")
        with self.assertRaisesRegex(ContextError, "coexist"):
            store.stage("job-B", "x", "STRING", "1")
        # Failed staging did not mutate previously committed values.
        store.discard_step("job-B")
        store.begin_step("run", "C", "job-C")
        self.assertEqual(store.read("job-C", "x", "STRING"), "123456")
        self.assertEqual(store.read("job-C", "y", "STRING"), "789012")
        store.end_run("run")

    def test_preflight_rejects_before_copy_in(self):
        class CountingCodec(FakeCodec):
            def __init__(self):
                self.copies = 0

            def copy_in(self, kind, value):
                self.copies += 1
                return super().copy_in(kind, value)

        codec = CountingCodec()
        store = ContextRegistry(codec, max_entry_bytes=12, max_total_bytes=12)
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "x", "STRING", "123456789012")
        self.assertEqual(codec.copies, 1)
        with self.assertRaisesRegex(ContextError, "budget"):
            store.stage("job-A", "y", "STRING", "over")
        self.assertEqual(codec.copies, 1)
        store.end_run("run")

    def test_abandoned_job_tombstone_blocks_late_native_write(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "x", "STRING", "partial")
        # Simulate a timeout or uncertain native job, after the orchestrator
        # disposed Context but the Comfy worker might still be executing.
        store.end_run("run")
        self.assertTrue(store.is_idle())
        self.assertTrue(store.was_abandoned_job("job-A"))
        self.assertFalse(store.was_abandoned_job("manual-job"))
        with self.assertRaises(ContextError):
            store.stage("job-A", "x", "STRING", "late")

    def test_abandoned_jobs_remain_bounded(self):
        store = registry()
        for i in range(1050):
            store.start_run(f"run-{i}")
            store.begin_step(f"run-{i}", "A", f"job-{i}")
            store.end_run(f"run-{i}")
        self.assertFalse(store.was_abandoned_job("job-0"))
        self.assertTrue(store.was_abandoned_job("job-1049"))
        self.assertLessEqual(len(store._retired_job_ids), 1024)

    def test_key_validation_and_run_cleanup(self):
        store = registry()
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        for bad in ("", " key", "a\nb", "a" * 129):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ContextError):
                    store.stage("job-A", bad, "STRING", "v")
        store.stage("job-A", "x", "STRING", "v")
        store.commit_step("job-A")
        store.end_run("run")
        store.start_run("new-run")
        self.assertEqual(store.manifest(), {})
        store.end_run("new-run")



    def test_inspection_reports_only_committed_metadata_without_values(self):
        store = registry()
        self.assertEqual(
            store.inspect(),
            {"active": False, "run_id": None, "active_job_id": None,
             "committed": {}, "total_bytes": 0},
        )
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "private-key", "STRING", "SECRET-DO-NOT-EXPOSE")
        self.assertEqual(store.inspect()["committed"], {})
        store.commit_step("job-A")
        inspection = store.inspect()
        self.assertTrue(inspection["active"])
        self.assertEqual(inspection["run_id"], "run")
        self.assertEqual(inspection["total_bytes"], len("SECRET-DO-NOT-EXPOSE"))
        self.assertEqual(
            inspection["committed"]["private-key"]["shape"],
            {"kind": "str"},
        )
        self.assertNotIn("SECRET-DO-NOT-EXPOSE", repr(inspection))
        store.end_run("run")
        self.assertFalse(store.inspect()["active"])
        self.assertEqual(store.inspect()["committed"], {})

    def test_context_survives_garbage_collection_between_native_jobs(self):
        """A model/cache cleanup must not release committed Context-owned data."""
        import gc
        import weakref

        class Source:
            pass

        store = registry()
        store.start_run("run")
        source = Source()
        weak = weakref.ref(source)
        payload = {"data": bytearray(b"safe-context")}
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "payload", "IMAGE", payload)
        store.commit_step("job-A")
        payload["data"][:] = b"bad-data-xxx"
        del source, payload
        gc.collect()
        self.assertIsNone(weak())
        store.begin_step("run", "B", "job-B")
        self.assertEqual(
            store.read("job-B", "payload", "IMAGE")["data"],
            bytearray(b"safe-context"),
        )
        store.commit_step("job-B")
        store.end_run("run")

    def test_context_shape_introspection_truncates_nested_containers(self):
        from workflowdirector.context import _describe_context_shape
        sample = {
            "tensor-like": {"data": [[1, 2, 3]]},
            "sequence": [1, 2, 3, 4, 5],
        }
        shape = _describe_context_shape(sample)
        self.assertEqual(shape["kind"], "dict")
        self.assertEqual(shape["fields"]["sequence"]["length"], 5)
        self.assertTrue(shape["fields"]["sequence"]["truncated"])
        self.assertEqual(
            shape["fields"]["sequence"]["items"][0], {"kind": "int"}
        )
        self.assertNotIn("1, 2, 3, 4, 5", repr(shape))



class StaticContextPlanTests(unittest.TestCase):
    def test_duplicate_literal_writers_are_rejected_before_queueing(self):
        prompt = {
            "1": {
                "class_type": "WorkflowDirectorContextPutString",
                "inputs": {"key": "same", "value": "a"},
            },
            "2": {
                "class_type": "WorkflowDirectorContextPutImage",
                "inputs": {"key": "same", "value": ["9", 0]},
            },
        }
        with self.assertRaisesRegex(RunRequestError, "Multiple Context Put"):
            parse_run_request({
                "steps": [{
                    "step_id": "A", "workflow_id": "wf-A",
                    "prompt": prompt, "workflow": {},
                }]
            })

    def test_cleanup_C_rejects_context_access_nodes_in_preflight(self):
        for bad_class in (
            "WorkflowDirectorContextPutUniversal",
            "WorkflowDirectorContextGetUniversal",
            "WorkflowDirectorContextPutString",
        ):
            with self.subTest(bad_class=bad_class):
                with self.assertRaisesRegex(
                    RunRequestError, "Cleanup must not contain Context nodes"
                ):
                    parse_run_request({
                        "steps": [{
                            "step_id": "C", "workflow_id": "wf-C",
                            "prompt": {
                                "1": {"class_type": bad_class, "inputs": {
                                    "key": "demo", "value": "x",
                                }},
                            },
                            "workflow": {},
                        }]
                    })

    def test_distinct_literal_writers_are_allowed(self):
        prompt = {
            "1": {
                "class_type": "WorkflowDirectorContextPutString",
                "inputs": {"key": "first", "value": "a"},
            },
            "2": {
                "class_type": "WorkflowDirectorContextPutImage",
                "inputs": {"key": "second", "value": ["9", 0]},
            },
        }
        plan, _ = parse_run_request({
            "steps": [{
                "step_id": "A", "workflow_id": "wf-A",
                "prompt": prompt, "workflow": {},
            }]
        })
        self.assertEqual(len(plan.steps), 1)


class NativeJobAdapterWithContext:
    def __init__(self, store, outcomes=None):
        self.store = store
        self.outcomes = outcomes or {}
        self.submitted = []
        self.b_read_value = None

    async def get_active_job_ids(self):
        return set()

    async def submit_prompt(self, *, prompt, workflow, prompt_id, client_id):
        self.submitted.append(prompt_id)
        if prompt["node"]["class_type"] == "A":
            self.store.stage(prompt_id, "shared", "STRING", "from-A")
        elif prompt["node"]["class_type"] == "B":
            self.b_read_value = self.store.read(prompt_id, "shared", "STRING")
        # C is deliberately a cleanup-only native job, without Context access.
        return prompt_id

    async def get_job_state(self, prompt_id):
        return self.outcomes.get(prompt_id, JobState.COMPLETED)


def plan():
    return RunPlan(
        run_id=str(uuid.uuid4()),
        steps=(
            PreparedStep("A", "wf-A", "A", {"node": {"class_type": "A"}}),
            PreparedStep("B", "wf-B", "B", {"node": {"class_type": "B"}}),
        ),
    )


class ContextLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_completed_A_patch_can_be_consumed_by_B(self):
        store = registry()
        adapter = NativeJobAdapterWithContext(store)
        engine = DirectorEngine(adapter, context=store)
        service = DirectorRunService(engine, context=store)
        p = plan()
        await service.start(p)
        record = await service.wait(p.run_id)
        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.b_read_value, "from-A")
        self.assertEqual(len(adapter.submitted), 2)
        self.assertEqual(
            record.context_manifest,
            {"shared": {"type": "STRING", "bytes": 6}},
        )
        self.assertTrue(
            any(event.kind == "context_committed" and event.step_id == "A"
                for event in record.events)
        )
        with self.assertRaises(ContextError):
            store.manifest()

    async def test_explicit_cleanup_C_preserves_committed_A_for_B(self):
        store = registry()
        adapter = NativeJobAdapterWithContext(store)
        p = RunPlan(
            run_id=str(uuid.uuid4()),
            steps=(
                PreparedStep("A", "wf-A", "A", {"node": {"class_type": "A"}}),
                PreparedStep("C", "wf-C", "Cleanup", {"node": {"class_type": "C"}}),
                PreparedStep("B", "wf-B", "B", {"node": {"class_type": "B"}}),
            ),
        )
        engine = DirectorEngine(adapter, context=store)
        service = DirectorRunService(engine, context=store)
        await service.start(p)
        record = await service.wait(p.run_id)
        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.b_read_value, "from-A")
        self.assertEqual(len(adapter.submitted), 3)
        self.assertEqual(
            record.context_manifest,
            {"shared": {"type": "STRING", "bytes": 6}},
        )
        self.assertEqual(
            [e.step_id for e in record.events if e.kind == "context_committed"],
            ["A", "C", "B"],
        )

    async def test_garbage_collecting_boundary_preserves_context_and_B_runs(self):
        import gc
        store = registry()
        adapter = NativeJobAdapterWithContext(store)

        class GarbageCollectBoundary:
            async def observe(self, *, step, job_id):
                gc.collect()
                return ()

        p = plan()
        engine = DirectorEngine(
            adapter, context=store,
            boundary_observer=GarbageCollectBoundary(),
        )
        service = DirectorRunService(engine, context=store)
        await service.start(p)
        record = await service.wait(p.run_id)
        self.assertEqual(record.phase, RunPhase.COMPLETED)
        self.assertEqual(adapter.b_read_value, "from-A")
        self.assertEqual(len(adapter.submitted), 2)

    async def test_corrupting_boundary_stops_before_B(self):
        store = registry()
        adapter = NativeJobAdapterWithContext(store)

        class DestructiveBoundary:
            async def observe(self, *, step, job_id):
                # Simulate a buggy future cleanup integration, NOT normal GC.
                store._session.values.clear()
                return ()

        p = plan()
        engine = DirectorEngine(
            adapter, context=store,
            boundary_observer=DestructiveBoundary(),
        )
        service = DirectorRunService(engine, context=store)
        await service.start(p)
        record = await service.wait(p.run_id)
        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(record.failure_code, "CONTEXT_CHANGED_AT_BOUNDARY")
        self.assertEqual(len(adapter.submitted), 1, "B must never start")

    async def test_failed_A_never_submits_B_or_commits_context(self):
        store = registry()
        adapter = NativeJobAdapterWithContext(store)
        p = plan()
        from workflowdirector.core.types import make_job_id
        adapter.outcomes[make_job_id(p.run_id, "A", 1)] = JobState.FAILED
        service = DirectorRunService(DirectorEngine(adapter, context=store), context=store)
        await service.start(p)
        record = await service.wait(p.run_id)
        self.assertEqual(record.phase, RunPhase.FAILED)
        self.assertEqual(len(adapter.submitted), 1)
        self.assertIsNone(adapter.b_read_value)
        with self.assertRaises(ContextError):
            store.manifest()
