"""Strict Torch codec for WorkflowDirector Context.

Torch is deliberately imported only when a Context node transfers tensors.
No MODEL/CLIP/VAE or arbitrary Python object can be stored in Context.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .context import ContextError, validate_type


class TorchContextCodec:
    """Stage copies in host memory and return independent host copies."""

    def __init__(self, *, max_tensor_bytes: int = 128 * 1024 * 1024) -> None:
        if max_tensor_bytes <= 0:
            raise ValueError("max_tensor_bytes must be positive")
        self._max_tensor_bytes = max_tensor_bytes

    def _copy_tensor(self, value: Any) -> tuple[Any, int]:
        import torch

        if not isinstance(value, torch.Tensor):
            raise ContextError(
                "IMAGE/LATENT must contain Torch tensors; model objects are forbidden"
            )
        if value.layout != torch.strided:
            raise ContextError("Only dense strided tensors are currently supported")
        if value.is_sparse or value.is_quantized or value.device.type == "meta":
            raise ContextError("Sparse, quantized and meta tensors are not supported")
        size = value.numel() * value.element_size()
        if size > self._max_tensor_bytes:
            raise ContextError("Tensor exceeds the safe Context CPU RAM limit")
        # Copy even CPU tensors: no reference to the source node or its GPU
        # storage must survive the prompt boundary.
        copy = value.detach().to(device="cpu", copy=True).contiguous()
        if copy.device.type != "cpu" or copy.requires_grad:
            raise ContextError("Context tensor must be detached and CPU resident")
        return copy, size

    def copy_in(self, kind: str, value: Any) -> tuple[Any, int]:
        validate_type(kind)
        if kind == "STRING":
            if not isinstance(value, str):
                raise ContextError("STRING Context requires a Python string")
            return value, len(value.encode("utf-8"))

        if kind == "IMAGE":
            return self._copy_tensor(value)

        if not isinstance(value, Mapping) or "samples" not in value:
            raise ContextError("LATENT Context requires a mapping with 'samples'")
        allowed = {"samples", "noise_mask", "batch_index", "type"}
        unknown = set(value) - allowed
        if unknown:
            raise ContextError(
                f"Unsupported LATENT metadata fields: {sorted(map(str, unknown))!r}"
            )

        result: dict[str, Any] = {}
        total = 0
        for name in ("samples", "noise_mask"):
            if name in value:
                copied, size = self._copy_tensor(value[name])
                result[name] = copied
                total += size
        if "batch_index" in value:
            indices = value["batch_index"]
            if not isinstance(indices, (list, tuple)) or not all(
                type(i) is int for i in indices
            ):
                raise ContextError("LATENT batch_index must be a sequence of integers")
            if len(indices) > 65536:
                raise ContextError("LATENT batch_index is too large")
            result["batch_index"] = list(indices)
            total += len(indices) * 8
        if "type" in value:
            latent_type = value["type"]
            if not isinstance(latent_type, str) or len(latent_type) > 128:
                raise ContextError("LATENT type metadata must be a short string")
            result["type"] = latent_type
            total += len(latent_type.encode("utf-8"))
        return result, total

    def copy_out(self, kind: str, value: Any) -> Any:
        validate_type(kind)
        if kind == "STRING":
            return value
        if kind == "IMAGE":
            return value.clone()
        # LATENT contents were strictly validated during staging.
        return {
            key: (entry.clone() if hasattr(entry, "clone")
                  and key in ("samples", "noise_mask") else
                  list(entry) if key == "batch_index" else entry)
            for key, entry in value.items()
        }
