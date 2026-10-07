"""Non-destructive run and boundary observations.

Nothing in this module unloads models, resets Comfy caches, calls /free, or
mutates model-management state.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .core import MemoryObservation, PreparedStep, RunPlan


SnapshotFn = Callable[[], Mapping[str, Any]]
SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]
ActiveJobsFn = Callable[[], Awaitable[set[str]]]


class BoundaryInterferenceError(RuntimeError):
    """Another Comfy job appeared during a Director observation boundary."""


class SnapshotRunObserver:
    """Capture a clean run baseline before the first Workflow.

    The optional warm-up call is deliberately discarded. It prevents first-use
    CUDA/device initialization from being confused with the BASELINE reading.
    """

    def __init__(
        self,
        *,
        snapshot: SnapshotFn,
        warm_up: bool = True,
    ) -> None:
        self._snapshot = snapshot
        self._warm_up = warm_up

    async def before_run(
        self,
        *,
        plan: RunPlan,
    ) -> tuple[MemoryObservation, ...]:
        if self._warm_up:
            self._snapshot()

        return (
            MemoryObservation.capture(
                "BASELINE",
                self._snapshot(),
            ),
        )


class ObservationBoundary:
    """Observe memory after a completed Workflow without cleaning anything.

    POST_IMMEDIATE is captured as soon as the Director sees native terminal
    completion and confirms that no unrelated Comfy job is active.

    POST_WINDOW_END is a second observation after a configurable idle window.
    The name intentionally does not imply that Comfy garbage collection ran or
    that memory reached a stable fixed point.

    When active_jobs is supplied, the boundary checks repeatedly for unrelated
    Comfy jobs. Any such job invalidates the boundary and stops the Master
    before the next Workflow is submitted.
    """

    def __init__(
        self,
        *,
        snapshot: SnapshotFn,
        observation_window_seconds: float,
        sample_interval_seconds: float = 0.25,
        active_jobs: ActiveJobsFn | None = None,
        clock: ClockFn = time.monotonic,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if observation_window_seconds < 0:
            raise ValueError("observation_window_seconds must be >= 0")
        if sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be > 0")

        self._snapshot = snapshot
        self._window = observation_window_seconds
        self._interval = sample_interval_seconds
        self._active_jobs = active_jobs
        self._clock = clock
        self._sleep = sleep

    async def observe(
        self,
        *,
        step: PreparedStep,
        job_id: str,
    ) -> tuple[MemoryObservation, ...]:
        observations = [
            await self._capture_quiet(
                label="POST_IMMEDIATE",
                step=step,
            )
        ]

        deadline = self._clock() + self._window
        while self._clock() < deadline:
            await self._sleep(
                min(
                    self._interval,
                    max(0.0, deadline - self._clock()),
                )
            )
            await self._assert_quiet(step=step)

        observations.append(
            await self._capture_quiet(
                label="POST_WINDOW_END",
                step=step,
            )
        )
        return tuple(observations)

    async def _capture_quiet(
        self,
        *,
        label: str,
        step: PreparedStep,
    ) -> MemoryObservation:
        await self._assert_quiet(step=step)
        snapshot = self._snapshot()
        await self._assert_quiet(step=step)
        return MemoryObservation.capture(label, snapshot)

    async def _assert_quiet(self, *, step: PreparedStep) -> None:
        if self._active_jobs is None:
            return

        active_ids = await self._active_jobs()
        if active_ids:
            raise BoundaryInterferenceError(
                (
                    f"Boundary after step {step.step_id} was contaminated by "
                    "active Comfy job(s): "
                    + ", ".join(sorted(active_ids))
                )
            )
