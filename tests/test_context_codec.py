"""Codec unit tests with a tiny Torch stand-in; no CUDA runner required."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from workflowdirector.context import ContextError
from workflowdirector.context_codec import TorchContextCodec


class FakeDevice:
    def __init__(self, kind):
        self.type = kind


class FakeTensor:
    is_sparse = False
    is_quantized = False

    def __init__(self, values, device="cuda", requires_grad=True):
        self.values = list(values)
        self.device = FakeDevice(device)
        self.requires_grad = requires_grad
        self.layout = "strided"

    def numel(self):
        return len(self.values)

    def element_size(self):
        return 4

    def detach(self):
        return FakeTensor(self.values, self.device.type, False)

    def to(self, *, device, copy):
        if not copy:
            raise AssertionError("Context must clone even CPU tensors")
        return FakeTensor(self.values, device, False)

    def contiguous(self):
        return self

    def clone(self):
        return FakeTensor(self.values, self.device.type, False)


class TorchContextCodecTests(unittest.TestCase):
    def setUp(self):
        module = types.SimpleNamespace(Tensor=FakeTensor, strided="strided")
        self.patcher = patch.dict(sys.modules, {"torch": module})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.codec = TorchContextCodec(max_tensor_bytes=128)

    def test_image_copy_is_host_owned_and_independent(self):
        source = FakeTensor([1, 2, 3])
        stored, size = self.codec.copy_in("IMAGE", source)
        self.assertEqual(size, 12)
        self.assertEqual(stored.device.type, "cpu")
        self.assertFalse(stored.requires_grad)
        source.values[0] = 99
        self.assertEqual(stored.values, [1, 2, 3])
        out = self.codec.copy_out("IMAGE", stored)
        out.values[1] = 88
        self.assertEqual(stored.values, [1, 2, 3])
        self.assertEqual(out.device.type, "cpu")

    def test_latent_copy_rejects_model_objects_and_clones_metadata(self):
        source = {
            "samples": FakeTensor([10, 20]),
            "noise_mask": FakeTensor([1, 0]),
            "batch_index": [0, 1],
        }
        stored, size = self.codec.copy_in("LATENT", source)
        self.assertEqual(size, 32)
        self.assertEqual(stored["samples"].device.type, "cpu")
        copy = self.codec.copy_out("LATENT", stored)
        copy["samples"].values[0] = 777
        copy["batch_index"][0] = 777
        self.assertEqual(stored["samples"].values, [10, 20])
        self.assertEqual(stored["batch_index"], [0, 1])
        with self.assertRaisesRegex(ContextError, "Unsupported LATENT metadata"):
            self.codec.copy_in(
                "LATENT", {"samples": FakeTensor([1]), "model": object()}
            )
        with self.assertRaisesRegex(ContextError, "Torch tensors"):
            self.codec.copy_in(
                "LATENT", {"samples": object()}
            )

    def test_rejects_overlarge_and_wrong_type(self):
        with self.assertRaisesRegex(ContextError, "safe Context"):
            self.codec.copy_in("IMAGE", FakeTensor(list(range(33))))
        with self.assertRaises(ContextError):
            self.codec.copy_in("MODEL", object())
        with self.assertRaises(ContextError):
            self.codec.copy_in("STRING", object())
