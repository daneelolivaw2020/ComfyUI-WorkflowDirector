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
from workflowdirector.core import (
    DirectorEngine,
    DirectorRunService,
    JobState,
    PreparedStep,
    RunPhase,
    RunPlan,
)


class FakeCodec:
    def copy_in(self, kind, value):
        if kind == "STRING":
            if not isinstance(value, str):
                raise ContextError("not a STRING")
            return value, len(value.encode("utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("data"), bytearray):
            raise ContextError("models are not allowed")
        return copy.deepcopy(value), len(value["data"])

    def copy_out(self, kind, value):
        return copy.deepcopy(value)


def registry(max_entry=128, max_total=256):
    return ContextRegistry(
        FakeCodec(),
        max_entry_bytes=max_entry,
        max_total_bytes=max_total,
    )


class ContextRegistryTests(unittest.TestCase):
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
        with self.assertRaisesRegex(ContextError, "CPU RAM limit"):
            store.stage("job-A", "b", "STRING", "1234567")
        with self.assertRaisesRegex(ContextError, "per-entry"):
            store.stage("job-A", "c", "STRING", "z" * 13)
        self.assertEqual(store.manifest(), {})
        store.discard_step("job-A")
        self.assertEqual(store.manifest(), {})
        store.end_run("run")

    def test_replacing_multiple_existing_keys_uses_effective_budget(self):
        store = registry(max_entry=12, max_total=12)
        store.start_run("run")
        store.begin_step("run", "A", "job-A")
        store.stage("job-A", "x", "STRING", "123456")
        store.stage("job-A", "y", "STRING", "789012")
        store.commit_step("job-A")
        store.begin_step("run", "B", "job-B")
        store.stage("job-B", "x", "STRING", "1")
        store.stage("job-B", "y", "STRING", "2")
        self.assertEqual(store.commit_step("job-B"), ("x", "y"))
        self.assertEqual(store.manifest()["x"]["bytes"], 1)
        self.assertEqual(store.manifest()["y"]["bytes"], 1)
        store.end_run("run")

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
        else:
            self.b_read_value = self.store.read(prompt_id, "shared", "STRING")
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
        self.assertTrue(
            any(event.kind == "context_committed" and event.step_id == "A"
                for event in record.events)
        )
        with self.assertRaises(ContextError):
            store.manifest()

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
