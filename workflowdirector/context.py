"""Run-scoped, transactional Context for independent ComfyUI jobs.

No ComfyUI, CUDA or Torch dependencies are imported by this module.
Only committed values are visible to downstream jobs. A job's staged writes
are discarded on failure, cancellation, unknown state or runtime teardown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol


class ContextError(RuntimeError):
    """Context cannot safely fulfill an operation."""


class ContextNotFound(ContextError):
    """The requested committed Context key does not exist."""


VALID_TYPES = frozenset(("STRING", "IMAGE", "LATENT"))


def validate_key(key: str) -> str:
    if not isinstance(key, str) or not key or len(key) > 128:
        raise ContextError("Context key must be a nonempty string of at most 128 characters")
    if key != key.strip() or any(ord(ch) < 32 for ch in key):
        raise ContextError("Context key must not have leading/trailing whitespace or controls")
    return key


def validate_type(kind: str) -> str:
    if kind not in VALID_TYPES:
        raise ContextError(
            f"Unsupported Context type {kind!r}; only STRING, IMAGE, LATENT are allowed. "
            "MODEL, CLIP, VAE and other live model objects are forbidden."
        )
    return kind


class ContextCodec(Protocol):
    """Convert values into detached CPU-safe copies; never keep caller references."""

    def copy_in(self, kind: str, value: Any) -> tuple[Any, int]: ...
    def copy_out(self, kind: str, value: Any) -> Any: ...


@dataclass(frozen=True)
class ContextValue:
    kind: str
    value: Any = field(repr=False)
    size_bytes: int


@dataclass
class StepPatch:
    run_id: str
    step_id: str
    job_id: str
    writes: dict[str, ContextValue] = field(default_factory=dict)


@dataclass
class ContextSession:
    run_id: str
    values: dict[str, ContextValue] = field(default_factory=dict)
    active_job_id: str | None = None
    total_bytes: int = 0


class ContextRegistry:
    """One active run, one active job and one atomic committed Context.

    A normal manual Comfy queue cannot access a Director Context transaction:
    job identities must have been registered by the Director before submission.
    All operations are synchronized across Comfy's prompt-worker thread and
    the Director's asyncio service thread.
    """

    def __init__(
        self,
        codec: ContextCodec,
        *,
        max_entry_bytes: int = 128 * 1024 * 1024,
        max_total_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        if max_entry_bytes <= 0 or max_total_bytes <= 0:
            raise ValueError("Context byte limits must be > 0")
        self._codec = codec
        self._max_entry_bytes = max_entry_bytes
        self._max_total_bytes = max_total_bytes
        self._lock = RLock()
        self._session: ContextSession | None = None
        self._patches: dict[str, StepPatch] = {}

    def is_idle(self) -> bool:
        """True only when there is no Director run owning Context."""
        with self._lock:
            return self._session is None

    def start_run(self, run_id: str) -> None:
        with self._lock:
            if self._session is not None:
                raise ContextError("A Context run is already active")
            if not run_id:
                raise ContextError("run_id must not be empty")
            self._session = ContextSession(run_id=run_id)

    def end_run(self, run_id: str) -> None:
        with self._lock:
            if self._session is None:
                return
            if self._session.run_id != run_id:
                raise ContextError("Cannot close Context owned by another run")
            # Drop all tensor references and uncommitted writes on every exit.
            self._patches.clear()
            self._session = None

    def begin_step(self, run_id: str, step_id: str, job_id: str) -> None:
        with self._lock:
            session = self._require_session()
            if session.run_id != run_id:
                raise ContextError("Context run id does not match the Director run")
            if session.active_job_id is not None or self._patches:
                raise ContextError("A Context step is already active")
            if not job_id or not step_id:
                raise ContextError("Context step and job identifiers must not be empty")
            session.active_job_id = job_id
            self._patches[job_id] = StepPatch(run_id, step_id, job_id)

    def stage(self, job_id: str, key: str, kind: str, value: Any) -> None:
        key = validate_key(key)
        kind = validate_type(kind)
        with self._lock:
            patch = self._require_patch(job_id)
            if key in patch.writes:
                raise ContextError(
                    f"Context key {key!r} has multiple writers in a single step"
                )
            # A model object is never accepted. A Torch tensor is detached,
            # copied to CPU and checked by the codec before being retained.
            stored, size_bytes = self._codec.copy_in(kind, value)
            if size_bytes < 0 or size_bytes > self._max_entry_bytes:
                raise ContextError(
                    f"Context value {key!r} exceeds the per-entry RAM limit"
                )
            session = self._require_session()
            # Charge the *effective* post-commit footprint, not the sum of
            # prior values plus every staged replacement. Each replacement
            # releases the previous logical entry at the commit boundary.
            projected = session.total_bytes
            for pending_key, pending_entry in patch.writes.items():
                old = session.values.get(pending_key)
                projected += pending_entry.size_bytes - (
                    old.size_bytes if old is not None else 0
                )
            previous = session.values.get(key)
            projected += size_bytes - (
                previous.size_bytes if previous is not None else 0
            )
            if projected > self._max_total_bytes:
                raise ContextError(
                    "Context would exceed its CPU RAM limit; scratch spilling "
                    "has not been enabled yet"
                )
            patch.writes[key] = ContextValue(kind, stored, size_bytes)

    def read(self, job_id: str, key: str, kind: str) -> Any:
        key = validate_key(key)
        kind = validate_type(kind)
        with self._lock:
            self._require_patch(job_id)
            session = self._require_session()
            entry = session.values.get(key)
            if entry is None:
                raise ContextNotFound(
                    f"Context key {key!r} has not been committed by an earlier step"
                )
            if entry.kind != kind:
                raise ContextError(
                    f"Context key {key!r} contains {entry.kind}, not {kind}"
                )
            # A caller must not mutate the committed value.
            return self._codec.copy_out(kind, entry.value)

    def commit_step(self, job_id: str) -> tuple[str, ...]:
        """Publish the entire patch only after terminal native Job COMPLETED."""
        with self._lock:
            patch = self._require_patch(job_id)
            session = self._require_session()
            merged = dict(session.values)
            merged.update(patch.writes)
            total = sum(entry.size_bytes for entry in merged.values())
            if total > self._max_total_bytes:
                raise ContextError("Committed Context would exceed the CPU RAM limit")
            session.values = merged
            session.total_bytes = total
            session.active_job_id = None
            del self._patches[job_id]
            return tuple(patch.writes)

    def discard_step(self, job_id: str) -> None:
        with self._lock:
            self._patches.pop(job_id, None)
            if self._session is not None and self._session.active_job_id == job_id:
                self._session.active_job_id = None

    def manifest(self) -> dict[str, dict[str, int | str]]:
        """Metadata only: do not expose tensors or other Python objects."""
        with self._lock:
            session = self._require_session()
            return {
                key: {"type": entry.kind, "bytes": entry.size_bytes}
                for key, entry in session.values.items()
            }

    def _require_session(self) -> ContextSession:
        if self._session is None:
            raise ContextError(
                "No active WorkflowDirector Context run. Use the Director, "
                "not Comfy's manual Queue, for Context nodes."
            )
        return self._session

    def _require_patch(self, job_id: str) -> StepPatch:
        session = self._require_session()
        patch = self._patches.get(job_id)
        if patch is None or session.active_job_id != job_id:
            raise ContextError(
                "This prompt is not the active WorkflowDirector Context job"
            )
        return patch
