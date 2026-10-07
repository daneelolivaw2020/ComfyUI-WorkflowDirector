"""Unit tests for the in-process Director run service."""

from __future__ import annotations

import asyncio
import unittest
import uuid

from workflowdirector.core import (
    ActiveRunError,
    DirectorRunService,
    DuplicateRunError,
    PreparedStep,
    RunPhase,
    RunPlan,
    RunRecord,
    RunNotFoundError,
)


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
        ),
    )


class BlockingEngine:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, plan, *, client_id=None, record=None):
        assert record is not None
        record.phase = RunPhase.RUNNING
        record.event("run_started")
        self.started.set()
        await self.release.wait()
        record.phase = RunPhase.COMPLETED
        record.event("run_completed")
        return record


class CrashingEngine:
    async def run(self, plan, *, client_id=None, record=None):
        assert record is not None
        record.phase = RunPhase.RUNNING
        raise RuntimeError("simulated engine crash")


class DirectorRunServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_exposes_same_live_record_object(self):
        engine = BlockingEngine()
        service = DirectorRunService(engine)
        plan = make_plan()

        started = await service.start(plan, client_id="browser")
        await engine.started.wait()

        live = service.get_record(plan.run_id)
        self.assertIs(started, live)
        self.assertEqual(live.phase, RunPhase.RUNNING)
        self.assertEqual(service.active_run_id, plan.run_id)

        engine.release.set()
        final = await service.wait(plan.run_id)

        self.assertIs(final, live)
        self.assertEqual(final.phase, RunPhase.COMPLETED)
        self.assertIsNone(service.active_run_id)

    async def test_second_director_run_is_rejected_while_first_is_active(self):
        engine = BlockingEngine()
        service = DirectorRunService(engine)
        first = make_plan()
        second = make_plan()

        await service.start(first)
        await engine.started.wait()

        with self.assertRaises(ActiveRunError):
            await service.start(second)

        engine.release.set()
        await service.wait(first.run_id)

    async def test_duplicate_run_id_is_not_reused(self):
        engine = BlockingEngine()
        service = DirectorRunService(engine)
        plan = make_plan()

        await service.start(plan)
        await engine.started.wait()
        engine.release.set()
        await service.wait(plan.run_id)

        with self.assertRaises(DuplicateRunError):
            await service.start(plan)

    async def test_engine_exception_becomes_failed_record(self):
        service = DirectorRunService(CrashingEngine())
        plan = make_plan()

        await service.start(plan)
        final = await service.wait(plan.run_id)

        self.assertEqual(final.phase, RunPhase.FAILED)
        self.assertEqual(final.failure_code, "INTERNAL_ERROR")
        self.assertIsNone(service.active_run_id)

    async def test_unknown_run_raises(self):
        service = DirectorRunService(BlockingEngine())

        with self.assertRaises(RunNotFoundError):
            service.get_record("missing")


if __name__ == "__main__":
    unittest.main()
