"""Universal Context regression tests without installing Torch or ComfyUI."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from workflowdirector.context import ContextError, ContextRegistry, validate_static_writers
from workflowdirector.context_codec import TorchContextCodec


class FakeDevice:
    def __init__(self, name):
        self.type = name


class FakeTensor:
    is_sparse = False
    is_quantized = False
    transfer_count = 0

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
            raise AssertionError("Universal Context cannot reuse input tensor storage")
        FakeTensor.transfer_count += 1
        return FakeTensor(self.values, device, False)

    def contiguous(self):
        return self

    def clone(self):
        return FakeTensor(self.values, self.device.type, False)


class UniversalContextTests(unittest.TestCase):
    def setUp(self):
        fake_torch = types.SimpleNamespace(Tensor=FakeTensor, strided="strided")
        patcher = patch.dict(sys.modules, {"torch": fake_torch})
        patcher.start()
        self.addCleanup(patcher.stop)
        FakeTensor.transfer_count = 0
        self.codec = TorchContextCodec(max_tensor_bytes=128)

    def test_conditioning_structure_is_cpu_owned_and_copy_out_is_independent(self):
        # A standard non-ControlNet CONDITIONING has embeddings and metadata.
        original = [[FakeTensor([1, 2]), {
            "pooled_output": FakeTensor([3, 4]),
            "strength": 0.5,
            "area": ("percentage", 0.5, 0.5, 0, 0),
        }]]
        store = ContextRegistry(self.codec, max_entry_bytes=512, max_total_bytes=1024)
        store.start_run("r")
        store.begin_step("r", "A", "a")
        store.stage("a", "positive.conditioning", "VALUE", original)
        self.assertEqual(store.manifest(), {})  # Staged entries must remain invisible.
        self.assertTrue(FakeTensor.transfer_count >= 2)
        store.commit_step("a")
        self.assertEqual(store.manifest()["positive.conditioning"]["type"], "VALUE")
        self.assertEqual(store.manifest()["positive.conditioning"]["bytes"],
                         self.codec.estimate_size("VALUE", original))
        original[0][0].values[0] = 999
        store.begin_step("r", "B", "b")
        first = store.read_any("b", "positive.conditioning")
        self.assertEqual(first[0][0].values, [1, 2])
        self.assertEqual(first[0][0].device.type, "cpu")
        self.assertEqual(first[0][1]["pooled_output"].device.type, "cpu")
        self.assertIsInstance(first[0][1]["area"], tuple)
        first[0][1]["pooled_output"].values[0] = 999
        self.assertEqual(store.read_any("b", "positive.conditioning")[0][1]
                         ["pooled_output"].values, [3, 4])
        store.commit_step("b")
        store.end_run("r")

    def test_rejects_model_reference_nested_inside_conditioning_before_copy(self):
        class FakeControlNet:
            pass
        source = [[FakeTensor([1, 2]), {"control": FakeControlNet()}]]
        store = ContextRegistry(self.codec)
        store.start_run("r")
        store.begin_step("r", "A", "a")
        with self.assertRaisesRegex(ContextError, "registered safe adapter"):
            store.stage("a", "unsafe", "VALUE", source)
        self.assertEqual(FakeTensor.transfer_count, 0)
        self.assertEqual(store.manifest(), {})
        store.end_run("r")

    def test_rejects_large_payload_before_cpu_copy(self):
        source = {"tensor": FakeTensor(list(range(32)))}
        store = ContextRegistry(self.codec, max_entry_bytes=8, max_total_bytes=20)
        store.start_run("r")
        store.begin_step("r", "A", "a")
        with self.assertRaisesRegex(ContextError, "per-entry"):
            store.stage("a", "huge", "VALUE", source)
        self.assertEqual(FakeTensor.transfer_count, 0)
        store.end_run("r")

    def test_rejects_tensor_above_per_tensor_limit(self):
        with self.assertRaisesRegex(ContextError, "per-tensor"):
            self.codec.estimate_size("VALUE", [FakeTensor(list(range(33)))])
        self.assertEqual(FakeTensor.transfer_count, 0)

    def test_cyclic_containers_and_opaque_objects_fail_closed(self):
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(ContextError, "cyclic"):
            self.codec.estimate_size("VALUE", cyclic)
        with self.assertRaisesRegex(ContextError, "registered safe adapter"):
            self.codec.copy_in("VALUE", object())
        with self.assertRaisesRegex(ContextError, "dict keys"):
            self.codec.copy_in("VALUE", {123: "value"})

    def test_tensor_subclass_rejected_before_custom_transfer(self):
        class TensorWithHiddenState(FakeTensor):
            def to(self, *, device, copy):
                raise AssertionError("Never call a custom tensor transfer method")
        value = {"model_attached_tensor": TensorWithHiddenState([1, 2])}
        with self.assertRaisesRegex(ContextError, "tensor subclasses"):
            self.codec.estimate_size("VALUE", value)
        with self.assertRaisesRegex(ContextError, "tensor subclasses"):
            self.codec.copy_in("VALUE", value)
        self.assertEqual(FakeTensor.transfer_count, 0)

    def test_plain_data_and_bytes_roundtrip(self):
        value = {"numbers": [3, 4.5, True, None], "raw": bytearray(b"abc")}
        stored, size = self.codec.copy_in("VALUE", value)
        self.assertEqual(size, self.codec.estimate_size("VALUE", value))
        out = self.codec.copy_out("VALUE", stored)
        out["raw"][0] = ord("z")
        self.assertEqual(stored["raw"], bytearray(b"abc"))

    def test_universal_get_can_consume_a_legacy_typed_entry(self):
        store = ContextRegistry(self.codec)
        store.start_run("r")
        store.begin_step("r", "A", "a")
        store.stage("a", "greeting", "STRING", "from A")
        store.commit_step("a")
        store.begin_step("r", "B", "b")
        self.assertEqual(store.read_any("b", "greeting"), "from A")
        with self.assertRaisesRegex(ContextError, "not VALUE"):
            store.read("b", "greeting", "VALUE")
        store.end_run("r")

    def test_static_duplicate_writer_rejected_with_universal_node(self):
        prompt = {
            "1": {"class_type": "WorkflowDirectorContextPutString",
                  "inputs": {"key": "same", "value": "first"}},
            "2": {"class_type": "WorkflowDirectorContextPutUniversal",
                  "inputs": {"key": "same", "value": ["1", 0]}},
        }
        with self.assertRaisesRegex(ContextError, "Multiple Context Put"):
            validate_static_writers(prompt)


if __name__ == "__main__":
    unittest.main()
