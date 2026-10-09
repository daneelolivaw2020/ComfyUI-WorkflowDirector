"""Conservative, extensible value transport across independent native jobs.

This is NOT pickle, Python deepcopy, or a memory reference store. Only plain
data containers and detached CPU tensor copies are transported. Unsupported
model/custom objects fail closed and require a future explicit adapter.
"""

from __future__ import annotations

from .context import ContextError


_MAX_DEPTH = 32
_MAX_PARTS = 10000


def _walk(value, *, clone: bool, max_tensor_bytes: int):
    import torch

    visiting: set[int] = set()
    visited_count = 0

    def walk(item, depth: int):
        nonlocal visited_count
        visited_count += 1
        if visited_count > _MAX_PARTS:
            raise ContextError("Universal Context value has too many components")
        if depth > _MAX_DEPTH:
            raise ContextError("Universal Context value is nested too deeply")

        kind = type(item)
        if item is None:
            return 0, None
        if kind is bool:
            return 1, item
        if kind is int:
            # Reject unreasonable integer magnitudes without retaining big buffers.
            if item.bit_length() > 4096:
                raise ContextError("Universal Context integer is too large")
            return len(str(item).encode("ascii")), item
        if kind is float:
            return 8, item
        if kind is str:
            return len(item.encode("utf-8")), item
        if kind is bytes:
            return len(item), item
        if kind is bytearray:
            return len(item), bytearray(item) if clone else None

        if isinstance(item, torch.Tensor):
            if (
                item.layout != torch.strided
                or item.is_sparse
                or item.is_quantized
                or item.device.type == "meta"
            ):
                raise ContextError("Universal Context supports only dense real tensors")
            size = item.numel() * item.element_size()
            if size > max_tensor_bytes:
                raise ContextError("Universal Context tensor exceeds the per-tensor RAM limit")
            if not clone:
                return size, None
            result = item.detach().to(device="cpu", copy=True).contiguous()
            if result.device.type != "cpu" or result.requires_grad:
                raise ContextError("Universal Context tensor must be detached and CPU resident")
            return size, result

        if kind not in (list, tuple, dict):
            raise ContextError(
                "Universal Context cannot safely retain "
                f"{kind.__module__}.{kind.__qualname__}; "
                "model or custom objects require a registered safe adapter"
            )

        obj_id = id(item)
        if obj_id in visiting:
            raise ContextError("Universal Context cannot retain cyclic containers")
        visiting.add(obj_id)
        try:
            if kind is dict:
                total = 0
                stored = {} if clone else None
                for key, child in item.items():
                    if type(key) is not str:
                        raise ContextError("Universal Context dict keys must be strings")
                    total += len(key.encode("utf-8"))
                    size, copy_child = walk(child, depth + 1)
                    total += size
                    if clone:
                        stored[key] = copy_child
            else:
                total = 0
                parts = [] if clone else None
                for child in item:
                    size, copy_child = walk(child, depth + 1)
                    total += size
                    if clone:
                        parts.append(copy_child)
                stored = tuple(parts) if clone and kind is tuple else parts
            return total, stored
        finally:
            visiting.remove(obj_id)

    return walk(value, 0)


def estimate_value(value, *, max_tensor_bytes: int) -> int:
    """Validate the entire tree BEFORE attempting a CUDA->CPU copy."""
    return _walk(value, clone=False, max_tensor_bytes=max_tensor_bytes)[0]


def clone_value(value, *, max_tensor_bytes: int):
    """Revalidate and reconstruct independent host-owned plain data."""
    return _walk(value, clone=True, max_tensor_bytes=max_tensor_bytes)[1]
