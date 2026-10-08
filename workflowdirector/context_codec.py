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

    def _estimate_tensor(self, value: Any) -> int:
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
        return size

    def _latent_fields(self, value: Any):
        if not isinstance(value, Mapping) or "samples" not in value:
            raise ContextError("LATENT Context requires a mapping with 'samples'")
        allowed = {"samples", "noise_mask", "batch_index", "type"}
        unknown = set(value) - allowed
        if unknown:
            raise ContextError(
                f"Unsupported LATENT metadata fields: {sorted(map(str, unknown))!r}"
            )
        return value

    def estimate_size(self, kind: str, value: Any) -> int:
        """Validate and estimate payload bytes before allocating CPU tensors."""
        validate_type(kind)
        if kind == "STRING":
            if not isinstance(value, str):
                raise ContextError("STRING Context requires a Python string")
            return len(value.encode("utf-8"))
        if kind == "IMAGE":
            return self._estimate_tensor(value)

        latent = self._latent_fields(value)
        total = self._estimate_tensor(latent["samples"])
        if "noise_mask" in latent:
            total += self._estimate_tensor(latent["noise_mask"])
        if "batch_index" in latent:
            indices = latent["batch_index"]
            if not isinstance(indices, (list, tuple)) or not all(
                type(i) is int for i in indices
            ):
                raise ContextError("LATENT batch_index must be a sequence of integers")
            if len(indices) > 65536:
                raise ContextError("LATENT batch_index is too large")
            total += len(indices) * 8
        if "type" in latent:
            latent_type = latent["type"]
            if not isinstance(latent_type, str) or len(latent_type) > 128:
                raise ContextError("LATENT type metadata must be a short string")
            total += len(latent_type.encode("utf-8"))
        return total

    def _copy_tensor(self, value: Any):
        size = self._estimate_tensor(value)
        # Always copy, even when already on CPU. Comfy's source tensor is
        # not owned by Context and may still reference a live execution.
        copy = value.detach().to(device="cpu", copy=True).contiguous()
        if copy.device.type != "cpu" or copy.requires_grad:
            raise ContextError("Context tensor must be detached and CPU resident")
        return copy, size

    def copy_in(self, kind: str, value: Any) -> tuple[Any, int]:
        size = self.estimate_size(kind, value)
        if kind == "STRING":
            return value, size
        if kind == "IMAGE":
            return self._copy_tensor(value)

        result: dict[str, Any] = {}
        for name in ("samples", "noise_mask"):
            if name in value:
                copied, _ = self._copy_tensor(value[name])
                result[name] = copied
        if "batch_index" in value:
            result["batch_index"] = list(value["batch_index"])
        if "type" in value:
            result["type"] = value["type"]
        return result, size

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
