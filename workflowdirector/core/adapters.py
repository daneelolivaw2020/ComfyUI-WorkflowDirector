"""Interfaces between the WorkflowDirector core and ComfyUI."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .types import JobState, MemoryObservation, PreparedStep, RunPlan


class AdapterTransportError(RuntimeError):
    """Transient transport/connectivity failure talking to the Comfy backend."""


class SubmissionTransportError(AdapterTransportError):
    """Submission may have reached ComfyUI but its acknowledgement was lost."""


class ComfyAdapter(Protocol):
    """Minimal execution contract required by the Director core."""

    async def submit_prompt(
        self,
        *,
        prompt: Mapping[str, Any],
        workflow: Mapping[str, Any],
        prompt_id: str,
        client_id: str | None,
    ) -> str:
        """Submit a prepared prompt using the supplied client-generated UUID.

        Return the prompt id acknowledged by ComfyUI.
        """

    async def get_job_state(self, prompt_id: str) -> JobState:
        """Return current/terminal native job state or UNKNOWN when not found."""

    async def get_active_job_ids(self) -> set[str]:
        """Return native pending/in-progress job ids visible to ComfyUI."""



class RunObserver(Protocol):
    """Observe run-level state before the first Workflow is submitted."""

    async def before_run(
        self,
        *,
        plan: RunPlan,
    ) -> Sequence[MemoryObservation]:
        ...


class NoopRunObserver:
    async def before_run(
        self,
        *,
        plan: RunPlan,
    ) -> Sequence[MemoryObservation]:
        return ()


class BoundaryObserver(Protocol):
    """Owns memory-boundary observation/policy outside prompt execution."""

    async def observe(
        self,
        *,
        step: PreparedStep,
        job_id: str,
    ) -> Sequence[MemoryObservation]:
        """Return only after the boundary is safe for the next Workflow."""


class NoopBoundaryObserver:
    """Useful for Phase 1 tests before real memory policy is connected."""

    async def observe(
        self,
        *,
        step: PreparedStep,
        job_id: str,
    ) -> Sequence[MemoryObservation]:
        return ()
