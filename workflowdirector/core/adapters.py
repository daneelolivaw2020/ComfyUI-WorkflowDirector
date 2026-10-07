"""Interfaces between the WorkflowDirector core and ComfyUI."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .types import JobState, MemoryObservation, PreparedStep


class SubmissionTransportError(RuntimeError):
    """Submission may have reached ComfyUI but its acknowledgement was lost."""


class ComfyAdapter(Protocol):
    """Minimal execution contract required by the Director core."""

    async def submit_prompt(
        self,
        *,
        prompt: Mapping[str, Any],
        prompt_id: str,
    ) -> str:
        """Submit a prepared prompt using the supplied client-generated UUID.

        Return the prompt id acknowledged by ComfyUI.
        """

    async def get_job_state(self, prompt_id: str) -> JobState:
        """Return current/terminal native job state or UNKNOWN when not found."""


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
