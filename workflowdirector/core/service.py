"""In-process Director run service.

The service owns live RunRecord objects and prevents multiple WorkflowDirector
Master runs from interleaving with each other. It is backend-agnostic and can be
unit-tested without ComfyUI.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from .director import DirectorEngine
from .types import RunPhase, RunPlan, RunRecord


class ActiveRunError(RuntimeError):
    """A WorkflowDirector run is already active."""


class DuplicateRunError(RuntimeError):
    """The requested run id already exists in this service."""


class RunNotFoundError(KeyError):
    """No run with the requested id exists."""


class EngineProtocol(Protocol):
    async def run(
        self,
        plan: RunPlan,
        *,
        client_id: str | None = None,
        record: RunRecord | None = None,
    ) -> RunRecord:
        ...


class DirectorRunService:
    """Own one active Director run and retain completed RunRecords."""

    def __init__(self, engine: EngineProtocol) -> None:
        self._engine = engine
        self._records: dict[str, RunRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._active_run_id: str | None = None
        self._start_lock = asyncio.Lock()

    @property
    def active_run_id(self) -> str | None:
        return self._active_run_id

    async def start(
        self,
        plan: RunPlan,
        *,
        client_id: str | None = None,
    ) -> RunRecord:
        async with self._start_lock:
            if self._active_run_id is not None:
                raise ActiveRunError(
                    f"Run {self._active_run_id} is already active"
                )
            if plan.run_id in self._records:
                raise DuplicateRunError(
                    f"Run {plan.run_id} already exists"
                )

            record = RunRecord(run_id=plan.run_id)
            self._records[plan.run_id] = record
            self._active_run_id = plan.run_id

            task = asyncio.create_task(
                self._execute(
                    plan=plan,
                    record=record,
                    client_id=client_id,
                ),
                name=f"workflowdirector:{plan.run_id}",
            )
            self._tasks[plan.run_id] = task
            return record

    def get_record(self, run_id: str) -> RunRecord:
        try:
            return self._records[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    async def wait(self, run_id: str) -> RunRecord:
        self.get_record(run_id)
        task = self._tasks.get(run_id)
        if task is not None:
            await task
        return self._records[run_id]

    async def _execute(
        self,
        *,
        plan: RunPlan,
        record: RunRecord,
        client_id: str | None,
    ) -> None:
        try:
            result = await self._engine.run(
                plan,
                client_id=client_id,
                record=record,
            )

            if result is not record:
                record.fail(
                    "ENGINE_RECORD_MISMATCH",
                    "Director engine returned a different RunRecord object",
                )
            elif record.phase in {RunPhase.READY, RunPhase.RUNNING}:
                record.fail(
                    "ENGINE_NON_TERMINAL",
                    "Director engine returned without a terminal run phase",
                )
        except asyncio.CancelledError:
            if record.phase in {RunPhase.READY, RunPhase.RUNNING}:
                record.phase = RunPhase.CANCELLED
                record.failure_code = "SERVICE_TASK_CANCELLED"
                record.failure_detail = "Director service task was cancelled"
                record.event("run_cancelled", detail=record.failure_detail)
            raise
        except Exception as exc:
            if record.phase in {RunPhase.READY, RunPhase.RUNNING}:
                record.fail(
                    "INTERNAL_ERROR",
                    f"{type(exc).__name__}: {exc}",
                )
        finally:
            if self._active_run_id == plan.run_id:
                self._active_run_id = None
            self._tasks.pop(plan.run_id, None)
