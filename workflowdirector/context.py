"""Run-scoped, transactional Context for independent ComfyUI jobs.

No ComfyUI, CUDA or Torch dependencies are imported by this module.
Only committed values are visible to downstream jobs. A job's staged writes
are discarded on failure, cancellation, unknown state or runtime teardown.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol


class ContextError(RuntimeError):
    """Context cannot safely fulfill an operation."""


class ContextNotFound(ContextError):
    """The requested committed Context key does not exist."""


VALID_TYPES = frozenset(("STRING", "IMAGE", "LATENT", "VALUE"))
_CONTEXT_PUT_NODES = frozenset((
    "WorkflowDirectorContextPutString",
    "WorkflowDirectorContextPutImage",
    "WorkflowDirectorContextPutLatent",
    "WorkflowDirectorContextPutUniversal",
))


def validate_static_writers(prompt: Mapping[str, Any]) -> None:
    """Reject duplicate literal Context Put keys before submitting heavy jobs.

    Dynamically linked key inputs are not statically resolvable and remain
    protected by ContextRegistry.stage() at native node execution.
    """
    if not hasattr(prompt, "values"):
        return
    found: set[str] = set()
    for node in prompt.values():
        if not isinstance(node, Mapping) or node.get("class_type") not in _CONTEXT_PUT_NODES:
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        key = inputs.get("key")
        if not isinstance(key, str):
            continue
        validate_key(key)
        if key in found:
            raise ContextError(
                f"Multiple Context Put nodes publish key {key!r} in one workflow"
            )
        found.add(key)



def validate_key(key: str) -> str:
    if not isinstance(key, str) or not key or len(key) > 128:
        raise ContextError("Context key must be a nonempty string of at most 128 characters")
    if key != key.strip() or any(ord(ch) < 32 for ch in key):
        raise ContextError("Context key must not have leading/trailing whitespace or controls")
    return key


def validate_type(kind: str) -> str:
    if kind not in VALID_TYPES:
        raise ContextError(
            f"Unsupported Context type {kind!r}; only STRING, IMAGE, LATENT, VALUE are allowed. "
            "MODEL, CLIP, VAE and other live model objects are forbidden."
        )
    return kind


class ContextCodec(Protocol):
    """Convert values into detached CPU-safe copies; never keep caller references."""

    def estimate_size(self, kind: str, value: Any) -> int: ...
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


def _describe_context_shape(value: Any, depth: int = 0) -> dict[str, Any]:
    """Metadata only: no strings, scalars, tensor contents or arbitrary reprs.

    Only inspect exact built-in container classes and exact Torch Tensor, so
    objects cannot execute user-defined __repr__/iteration/attribute hooks.
    This is intentionally shallow to cap UI/HTTP response size.
    """
    kind = type(value)
    if value is None:
        return {"kind": "none"}
    if kind in (str, bytes, bytearray, int, float, bool):
        return {"kind": kind.__name__}
    # Import Torch only for values already stored; normally it is loaded by
    # the codec, not by the Context service startup path.
    if kind.__module__ == "torch" and kind.__name__ == "Tensor":
        return {
            "kind": "tensor",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "device": value.device.type,
        }
    if depth >= 3:
        return {"kind": kind.__name__, "truncated": True}
    if kind is dict:
        # Only exact dicts holding string keys enter universal storage.
        shown = list(value.items())[:8]
        return {
            "kind": "dict", "length": len(value),
            "fields": {
                str(key): _describe_context_shape(child, depth + 1)
                for key, child in shown
            },
            "truncated": len(value) > len(shown),
        }
    if kind in (list, tuple):
        shown = value[:4]
        return {
            "kind": kind.__name__, "length": len(value),
            "items": [_describe_context_shape(child, depth + 1) for child in shown],
            "truncated": len(value) > len(shown),
        }
    return {"kind": "opaque"}


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
        # Bounded tombstones stop late native callbacks from a timed-out or
        # aborted Director job masquerading as a normal manual Queue prompt.
        self._retired_job_ids: set[str] = set()
        self._retired_job_order: deque[str] = deque(maxlen=1024)

    def is_idle(self) -> bool:
        """True only when there is no Director run owning Context."""
        with self._lock:
            return self._session is None

    def was_abandoned_job(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._retired_job_ids

    def _retire_job(self, job_id: str) -> None:
        if job_id in self._retired_job_ids:
            return
        if len(self._retired_job_order) == self._retired_job_order.maxlen:
            evicted = self._retired_job_order.popleft()
            self._retired_job_ids.discard(evicted)
        self._retired_job_order.append(job_id)
        self._retired_job_ids.add(job_id)

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
            # An aborted native job might still be running after the
            # orchestrator timed out. Do not treat its eventual Put as manual
            # pass-through; the caller must see an explicit error.
            for job_id in self._patches:
                self._retire_job(job_id)
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
            session = self._require_session()
            # Preflight *before* moving a CUDA tensor to host RAM. Account
            # for committed and staged payloads coexisting until commit.
            estimate = self._codec.estimate_size(kind, value)
            if estimate < 0 or estimate > self._max_entry_bytes:
                raise ContextError(
                    f"Context value {key!r} exceeds the per-entry RAM limit"
                )
            pending_bytes = sum(entry.size_bytes for entry in patch.writes.values())
            if session.total_bytes + pending_bytes + estimate > self._max_total_bytes:
                raise ContextError(
                    "Context would exceed its CPU RAM budget while old and new "
                    "values coexist; scratch spilling is not implemented yet"
                )
            stored, size_bytes = self._codec.copy_in(kind, value)
            if size_bytes != estimate:
                raise ContextError(
                    "Context codec size mismatch; refusing to retain unchecked data"
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

    def read_any(self, job_id: str, key: str) -> Any:
        """Read a committed entry regardless of its legacy or universal kind.

        Returned data is always independently cloned by the trusted codec.
        The consumer still must be compatible with the actual runtime value.
        """
        key = validate_key(key)
        with self._lock:
            self._require_patch(job_id)
            session = self._require_session()
            entry = session.values.get(key)
            if entry is None:
                raise ContextNotFound(
                    f"Context key {key!r} has not been committed by an earlier step"
                )
            return self._codec.copy_out(entry.kind, entry.value)

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
            if self._patches.pop(job_id, None) is not None:
                self._retire_job(job_id)
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

    def inspect(self) -> dict[str, Any]:
        """Bounded, read-only structural view; never expose payload values.

        Safe to call during an active run, including between native jobs. The
        registry lock ensures each snapshot belongs to one committed version.
        Staged writes stay invisible until their native job is COMPLETED.
        """
        with self._lock:
            session = self._session
            if session is None:
                return {
                    "active": False, "run_id": None, "active_job_id": None,
                    "committed": {}, "total_bytes": 0,
                }
            return {
                "active": True,
                "run_id": session.run_id,
                "active_job_id": session.active_job_id,
                "committed": {
                    key: {
                        "type": entry.kind,
                        "bytes": entry.size_bytes,
                        "shape": _describe_context_shape(entry.value),
                    }
                    for key, entry in session.values.items()
                },
                "total_bytes": session.total_bytes,
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
