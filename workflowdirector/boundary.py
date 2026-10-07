"""Initial non-destructive memory-boundary observation.

This observer never unloads models, resets caches, or calls ComfyUI /free.
Its only job is to record post-workflow memory while the queue remains under
Director control.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .core import MemoryObservation, PreparedStep


SnapshotFn = Callable[[], Mapping[str, Any]]
SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]


class ObservationBoundary:
    """Record immediate and end-of-window memory observations without cleanup.

    The minimum observation time is an integration/lab policy, not a universal
    ComfyUI truth. Future settling policies can replace this observer without
    changing DirectorEngine.
    """

    def __init__(
        self,
        *,
        snapshot: SnapshotFn,
        minimum_observation_seconds: float,
        sample_interval_seconds: float = 1.0,
        clock: ClockFn = time.monotonic,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if minimum_observation_seconds < 0:
            raise ValueError("minimum_observation_seconds must be >= 0")
        if sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be > 0")

        self._snapshot = snapshot
        self._minimum = minimum_observation_seconds
        self._interval = sample_interval_seconds
        self._clock = clock
        self._sleep = sleep

    async def observe(
        self,
        *,
        step: PreparedStep,
        job_id: str,
    ) -> tuple[MemoryObservation, ...]:
        start = self._clock()
        observations = [
            MemoryObservation.capture(
                "POST_IMMEDIATE",
                self._snapshot(),
            )
        ]

        while self._clock() - start < self._minimum:
            await self._sleep(
                min(
                    self._interval,
                    max(0.0, self._minimum - (self._clock() - start)),
                )
            )

        observations.append(
            MemoryObservation.capture(
                "POST_WINDOW_END",
                self._snapshot(),
            )
        )
        return tuple(observations)
