"""Core immutable/mutable records for WorkflowDirector.

This module deliberately has no dependency on ComfyUI. The core state machine
can therefore be unit-tested without a GPU or a running Comfy backend.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping
import json
import time
import uuid


class JobState(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunPhase(str, Enum):
    READY = "ready"
    RUNNING = "running"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass(frozen=True, init=False)
class PreparedStep:
    """One immutable workflow execution inside a prepared RunPlan.

    The executable prompt is stored as canonical JSON instead of as a caller-
    owned dict. Accessing the prompt property returns a fresh decoded object, so
    edits elsewhere cannot mutate an already-prepared run.
    """

    step_id: str
    workflow_id: str
    name: str
    _prompt_json: str = field(repr=False)

    def __init__(
        self,
        step_id: str,
        workflow_id: str,
        name: str,
        prompt: Mapping[str, Any],
    ) -> None:
        if not step_id:
            raise ValueError("step_id cannot be empty")
        if not workflow_id:
            raise ValueError("workflow_id cannot be empty")

        encoded = json.dumps(
            prompt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "workflow_id", workflow_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "_prompt_json", encoded)

    @property
    def prompt(self) -> Mapping[str, Any]:
        return json.loads(self._prompt_json)


@dataclass(frozen=True)
class RunPlan:
    """Immutable set of prepared workflow steps for one Master run."""

    run_id: str
    steps: tuple[PreparedStep, ...]

    def __post_init__(self) -> None:
        uuid.UUID(self.run_id)
        object.__setattr__(self, "steps", tuple(self.steps))

        if not self.steps:
            raise ValueError("RunPlan requires at least one step")

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("RunPlan step_id values must be unique")

    @classmethod
    def create(cls, steps: tuple[PreparedStep, ...]) -> "RunPlan":
        return cls(run_id=str(uuid.uuid4()), steps=steps)


def make_job_id(run_id: str, step_id: str, attempt: int) -> str:
    """Return a stable UUID for one run/step/attempt."""

    if attempt < 1:
        raise ValueError("attempt must be >= 1")

    namespace = uuid.UUID(run_id)
    return str(uuid.uuid5(namespace, f"{step_id}:{attempt}"))


@dataclass(frozen=True)
class MemoryObservation:
    label: str
    captured_at: float
    snapshot: Mapping[str, Any]

    @classmethod
    def capture(cls, label: str, snapshot: Mapping[str, Any]) -> "MemoryObservation":
        return cls(label=label, captured_at=time.time(), snapshot=dict(snapshot))


@dataclass
class JobAttemptRecord:
    step_id: str
    workflow_id: str
    attempt: int
    job_id: str
    state: JobState = JobState.UNKNOWN
    observations: list[MemoryObservation] = field(default_factory=list)


@dataclass(frozen=True)
class RunEvent:
    kind: str
    step_id: str | None = None
    job_id: str | None = None
    detail: str | None = None
    at: float = field(default_factory=time.time)


@dataclass
class RunRecord:
    run_id: str
    phase: RunPhase = RunPhase.READY
    current_step_index: int | None = None
    attempts: list[JobAttemptRecord] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    failure_code: str | None = None
    failure_detail: str | None = None

    def event(
        self,
        kind: str,
        *,
        step_id: str | None = None,
        job_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.events.append(
            RunEvent(
                kind=kind,
                step_id=step_id,
                job_id=job_id,
                detail=detail,
            )
        )

    def fail(self, code: str, detail: str) -> None:
        self.phase = RunPhase.FAILED
        self.failure_code = code
        self.failure_detail = detail
        self.event("run_failed", detail=f"{code}: {detail}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation suitable for persistence."""

        data = asdict(self)
        data["phase"] = self.phase.value

        for attempt in data["attempts"]:
            state = attempt.get("state")
            if isinstance(state, Enum):
                attempt["state"] = state.value

        return data
