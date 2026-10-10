"""Workflow-level state machine.

The Director is intentionally not a Comfy node and never runs inside
PromptExecutor. It submits exactly one prepared Workflow job at a time, waits
for native terminal state, runs the boundary observer, and only then advances.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from .adapters import (
    AdapterTransportError,
    BoundaryObserver,
    ComfyAdapter,
    NoopBoundaryObserver,
    NoopRunObserver,
    RunObserver,
    SubmissionTransportError,
)
from .types import (
    JobAttemptRecord,
    JobState,
    RunPhase,
    RunPlan,
    RunRecord,
    make_job_id,
)


SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]


class DirectorEngine:
    def __init__(
        self,
        adapter: ComfyAdapter,
        *,
        boundary_observer: BoundaryObserver | None = None,
        run_observer: RunObserver | None = None,
        context=None,
        poll_interval_seconds: float = 0.25,
        job_timeout_seconds: float = 3600.0,
        submission_recovery_timeout_seconds: float = 5.0,
        sleep: SleepFn = asyncio.sleep,
        clock: ClockFn = time.monotonic,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")
        if job_timeout_seconds <= 0:
            raise ValueError("job_timeout_seconds must be > 0")
        if submission_recovery_timeout_seconds <= 0:
            raise ValueError("submission_recovery_timeout_seconds must be > 0")

        self._adapter = adapter
        self._boundary = boundary_observer or NoopBoundaryObserver()
        self._run_observer = run_observer or NoopRunObserver()
        self._context = context
        self._poll_interval = poll_interval_seconds
        self._job_timeout = job_timeout_seconds
        self._submission_recovery_timeout = submission_recovery_timeout_seconds
        self._sleep = sleep
        self._clock = clock

    async def run(
        self,
        plan: RunPlan,
        *,
        client_id: str | None = None,
        record: RunRecord | None = None,
    ) -> RunRecord:
        """Execute one prepared plan.

        client_id is ephemeral frontend routing state. It is intentionally not
        part of the immutable RunPlan.
        """

        if record is None:
            record = RunRecord(run_id=plan.run_id)

        if record.run_id != plan.run_id:
            raise ValueError("RunRecord run_id must match RunPlan run_id")
        if record.phase != RunPhase.READY:
            raise ValueError("RunRecord must be READY before execution starts")

        record.phase = RunPhase.RUNNING
        record.event("run_started")

        if not await self._ensure_queue_exclusive(
            record=record,
            step_id=None,
        ):
            return record

        try:
            observations = await self._run_observer.before_run(plan=plan)
            record.observations.extend(observations)
        except Exception as exc:
            record.fail(
                "RUN_OBSERVER_FAILED",
                f"{type(exc).__name__}: {exc}",
            )
            return record

        record.event("run_observer_completed")

        for index, step in enumerate(plan.steps):
            record.current_step_index = index
            attempt_number = 1
            job_id = make_job_id(plan.run_id, step.step_id, attempt_number)
            attempt = JobAttemptRecord(
                step_id=step.step_id,
                workflow_id=step.workflow_id,
                attempt=attempt_number,
                job_id=job_id,
            )
            record.attempts.append(attempt)

            if not await self._ensure_queue_exclusive(
                record=record,
                step_id=step.step_id,
            ):
                return record

            record.event(
                "submission_started",
                step_id=step.step_id,
                job_id=job_id,
            )

            if self._context is not None:
                try:
                    self._context.begin_step(plan.run_id, step.step_id, job_id)
                except Exception as exc:
                    record.fail(
                        "CONTEXT_BEGIN_FAILED",
                        f"{type(exc).__name__}: {exc}",
                    )
                    return record

            acknowledged = await self._submit_or_recover(
                record=record,
                step_id=step.step_id,
                job_id=job_id,
                prompt=step.prompt,
                workflow=step.workflow,
                client_id=client_id,
            )
            if not acknowledged:
                return record

            terminal = await self._wait_for_terminal(
                record=record,
                attempt=attempt,
            )
            if terminal is None:
                return record

            if terminal == JobState.FAILED:
                record.fail(
                    "JOB_FAILED",
                    f"Workflow step {step.step_id} failed ({job_id})",
                )
                return record

            if terminal == JobState.CANCELLED:
                record.phase = RunPhase.CANCELLED
                record.failure_code = "JOB_CANCELLED"
                record.failure_detail = (
                    f"Workflow step {step.step_id} was cancelled ({job_id})"
                )
                record.event(
                    "run_cancelled",
                    step_id=step.step_id,
                    job_id=job_id,
                )
                return record

            if self._context is not None:
                try:
                    published_keys = self._context.commit_step(job_id)
                    record.context_manifest = self._context.manifest()
                    record.context_inspection = self._context.inspect()["committed"]
                    record.event(
                        "context_committed",
                        step_id=step.step_id,
                        job_id=job_id,
                        detail=", ".join(published_keys),
                    )
                except Exception as exc:
                    record.fail(
                        "CONTEXT_COMMIT_FAILED",
                        f"{type(exc).__name__}: {exc}",
                    )
                    return record

            try:
                observations = await self._boundary.observe(
                    step=step,
                    job_id=job_id,
                )
                attempt.observations.extend(observations)
            except Exception as exc:
                record.fail(
                    "BOUNDARY_FAILED",
                    f"{type(exc).__name__}: {exc}",
                )
                return record

            # Cleanup must NEVER erase/replace committed Context. The
            # registry holds detached CPU copies, and we also verify its
            # committed metadata survived the boundary before submitting B.
            # This is a structural guard (not a tensor-content checksum).
            if self._context is not None:
                try:
                    after_boundary = self._context.manifest()
                    if after_boundary != record.context_manifest:
                        record.fail(
                            "CONTEXT_CHANGED_AT_BOUNDARY",
                            "Committed Context keys/sizes changed during the "
                            f"boundary after step {step.step_id}; refusing the "
                            "next native job",
                        )
                        return record
                except Exception as exc:
                    record.fail(
                        "CONTEXT_BOUNDARY_CHECK_FAILED",
                        f"{type(exc).__name__}: {exc}",
                    )
                    return record

            record.event(
                "boundary_completed",
                step_id=step.step_id,
                job_id=job_id,
            )

        record.current_step_index = None
        record.phase = RunPhase.COMPLETED
        record.event("run_completed")
        return record

    async def _ensure_queue_exclusive(
        self,
        *,
        record: RunRecord,
        step_id: str | None,
    ) -> bool:
        """Refuse to submit while any unrelated Comfy job is active."""

        try:
            active_ids = await self._adapter.get_active_job_ids()
        except AdapterTransportError as exc:
            record.fail(
                "QUEUE_STATE_UNCERTAIN",
                f"Could not verify active Comfy jobs: {exc}",
            )
            return False
        except Exception as exc:
            record.fail(
                "QUEUE_STATE_FAILED",
                f"{type(exc).__name__}: {exc}",
            )
            return False

        if active_ids:
            scope = f"step {step_id}" if step_id is not None else "run baseline"
            record.fail(
                "QUEUE_NOT_EXCLUSIVE",
                (
                    f"Cannot continue {scope}; Comfy has active job(s): "
                    + ", ".join(sorted(active_ids))
                ),
            )
            return False

        record.event(
            "queue_exclusive",
            step_id=step_id,
        )
        return True

    async def _submit_or_recover(
        self,
        *,
        record: RunRecord,
        step_id: str,
        job_id: str,
        prompt,
        workflow,
        client_id: str | None,
    ) -> bool:
        try:
            acknowledged_id = await self._adapter.submit_prompt(
                prompt=prompt,
                workflow=workflow,
                prompt_id=job_id,
                client_id=client_id,
            )
        except SubmissionTransportError as exc:
            record.event(
                "submission_ack_lost",
                step_id=step_id,
                job_id=job_id,
                detail=str(exc),
            )
            state = await self._wait_for_submission_visibility(
                record=record,
                step_id=step_id,
                job_id=job_id,
            )
            if state is None:
                return False

            record.event(
                "submission_recovered",
                step_id=step_id,
                job_id=job_id,
                detail=state.value,
            )
            return True
        except Exception as exc:
            record.fail(
                "SUBMISSION_FAILED",
                f"{type(exc).__name__}: {exc}",
            )
            return False

        if acknowledged_id != job_id:
            record.fail(
                "JOB_ID_MISMATCH",
                f"Expected {job_id}, backend acknowledged {acknowledged_id}",
            )
            return False

        record.event(
            "submission_acknowledged",
            step_id=step_id,
            job_id=job_id,
        )
        return True

    async def _wait_for_submission_visibility(
        self,
        *,
        record: RunRecord,
        step_id: str,
        job_id: str,
    ) -> JobState | None:
        deadline = self._clock() + self._submission_recovery_timeout

        while True:
            try:
                state = await self._adapter.get_job_state(job_id)
            except AdapterTransportError as lookup_exc:
                record.event(
                    "submission_lookup_transport_error",
                    step_id=step_id,
                    job_id=job_id,
                    detail=str(lookup_exc),
                )
            except Exception as lookup_exc:
                record.fail(
                    "SUBMISSION_UNCERTAIN",
                    (
                        "Submission acknowledgement was lost and job lookup "
                        f"failed: {type(lookup_exc).__name__}: {lookup_exc}"
                    ),
                )
                return None
            else:
                if state != JobState.UNKNOWN:
                    return state

            if self._clock() >= deadline:
                record.fail(
                    "SUBMISSION_UNCERTAIN",
                    (
                        "Submission acknowledgement was lost and the prepared "
                        f"job id {job_id} remained unobservable. "
                        "Refusing to resubmit."
                    ),
                )
                return None

            await self._sleep(
                min(
                    self._poll_interval,
                    max(0.0, deadline - self._clock()),
                )
            )

    async def _ensure_only_expected_job_active(
        self,
        *,
        record: RunRecord,
        attempt: JobAttemptRecord,
    ) -> bool:
        """Fail closed if another Comfy job appears while ours is active."""

        try:
            active_ids = await self._adapter.get_active_job_ids()
        except AdapterTransportError as exc:
            record.fail(
                "QUEUE_STATE_UNCERTAIN",
                f"Could not verify active Comfy jobs during execution: {exc}",
            )
            return False
        except Exception as exc:
            record.fail(
                "QUEUE_STATE_FAILED",
                f"{type(exc).__name__}: {exc}",
            )
            return False

        foreign_ids = active_ids - {attempt.job_id}
        if foreign_ids:
            record.fail(
                "QUEUE_INTERFERENCE",
                (
                    f"Unexpected Comfy job(s) appeared while step "
                    f"{attempt.step_id} was active: "
                    + ", ".join(sorted(foreign_ids))
                ),
            )
            return False

        return True

    async def _wait_for_terminal(
        self,
        *,
        record: RunRecord,
        attempt: JobAttemptRecord,
    ) -> JobState | None:
        deadline = self._clock() + self._job_timeout
        last_state: JobState | None = None

        while True:
            try:
                state = await self._adapter.get_job_state(attempt.job_id)
            except AdapterTransportError as exc:
                record.event(
                    "job_status_transport_error",
                    step_id=attempt.step_id,
                    job_id=attempt.job_id,
                    detail=str(exc),
                )
            except Exception as exc:
                record.fail(
                    "JOB_STATUS_FAILED",
                    f"{type(exc).__name__}: {exc}",
                )
                return None
            else:
                attempt.state = state

                if state != last_state:
                    record.event(
                        "job_state",
                        step_id=attempt.step_id,
                        job_id=attempt.job_id,
                        detail=state.value,
                    )
                    last_state = state

                if state not in {
                    JobState.COMPLETED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                }:
                    if not await self._ensure_only_expected_job_active(
                        record=record,
                        attempt=attempt,
                    ):
                        return None

                if state in {
                    JobState.COMPLETED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                }:
                    return state

            if self._clock() >= deadline:
                record.fail(
                    "JOB_STATUS_TIMEOUT",
                    f"Job {attempt.job_id} did not reach terminal state in time",
                )
                return None

            await self._sleep(
                min(
                    self._poll_interval,
                    max(0.0, deadline - self._clock()),
                )
            )
