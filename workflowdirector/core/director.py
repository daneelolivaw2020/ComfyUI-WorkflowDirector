"""Workflow-level state machine.

The Director is intentionally not a Comfy node and never runs inside
PromptExecutor.  It submits exactly one prepared Workflow job at a time, waits
for native terminal state, runs the boundary observer, and only then advances.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .adapters import (
    BoundaryObserver,
    ComfyAdapter,
    NoopBoundaryObserver,
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


class DirectorEngine:
    def __init__(
        self,
        adapter: ComfyAdapter,
        *,
        boundary_observer: BoundaryObserver | None = None,
        poll_interval_seconds: float = 0.25,
        max_polls_per_job: int = 2400,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be >= 0")
        if max_polls_per_job < 1:
            raise ValueError("max_polls_per_job must be >= 1")

        self._adapter = adapter
        self._boundary = boundary_observer or NoopBoundaryObserver()
        self._poll_interval = poll_interval_seconds
        self._max_polls = max_polls_per_job
        self._sleep = sleep

    async def run(self, plan: RunPlan) -> RunRecord:
        record = RunRecord(run_id=plan.run_id, phase=RunPhase.RUNNING)
        record.event("run_started")

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

            record.event(
                "submission_started",
                step_id=step.step_id,
                job_id=job_id,
            )

            acknowledged = await self._submit_or_recover(
                record=record,
                step_id=step.step_id,
                job_id=job_id,
                prompt=step.prompt,
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

            try:
                observations = await self._boundary.observe(
                    step=step,
                    job_id=job_id,
                )
            except Exception as exc:
                record.fail(
                    "BOUNDARY_FAILED",
                    f"{type(exc).__name__}: {exc}",
                )
                return record

            attempt.observations.extend(observations)
            record.event(
                "boundary_completed",
                step_id=step.step_id,
                job_id=job_id,
            )

        record.current_step_index = None
        record.phase = RunPhase.COMPLETED
        record.event("run_completed")
        return record

    async def _submit_or_recover(
        self,
        *,
        record: RunRecord,
        step_id: str,
        job_id: str,
        prompt,
    ) -> bool:
        try:
            acknowledged_id = await self._adapter.submit_prompt(
                prompt=prompt,
                prompt_id=job_id,
            )
        except SubmissionTransportError as exc:
            # The request may have reached ComfyUI.  Never blindly resubmit.
            record.event(
                "submission_ack_lost",
                step_id=step_id,
                job_id=job_id,
                detail=str(exc),
            )
            try:
                state = await self._adapter.get_job_state(job_id)
            except Exception as lookup_exc:
                record.fail(
                    "SUBMISSION_UNCERTAIN",
                    (
                        "Submission acknowledgement was lost and job lookup "
                        f"also failed: {type(lookup_exc).__name__}: {lookup_exc}"
                    ),
                )
                return False

            if state == JobState.UNKNOWN:
                record.fail(
                    "SUBMISSION_UNCERTAIN",
                    (
                        "Submission acknowledgement was lost and the prepared "
                        f"job id {job_id} is not observable. Refusing to resubmit."
                    ),
                )
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

    async def _wait_for_terminal(
        self,
        *,
        record: RunRecord,
        attempt: JobAttemptRecord,
    ) -> JobState | None:
        last_state: JobState | None = None

        for _ in range(self._max_polls):
            try:
                state = await self._adapter.get_job_state(attempt.job_id)
            except Exception as exc:
                record.fail(
                    "JOB_STATUS_FAILED",
                    f"{type(exc).__name__}: {exc}",
                )
                return None

            attempt.state = state

            if state != last_state:
                record.event(
                    "job_state",
                    step_id=attempt.step_id,
                    job_id=attempt.job_id,
                    detail=state.value,
                )
                last_state = state

            if state in {
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
            }:
                return state

            # UNKNOWN is tolerated here because a just-accepted job may not yet
            # be visible through every status surface.  It becomes a timeout,
            # never an automatic duplicate submission.
            await self._sleep(self._poll_interval)

        record.fail(
            "JOB_STATUS_TIMEOUT",
            f"Job {attempt.job_id} did not reach terminal state in time",
        )
        return None
