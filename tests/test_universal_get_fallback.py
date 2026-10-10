"""Isolated V3 Context GET tests without requiring a Comfy installation.

Compile the actual node class AST with stubbed Comfy V3 I/O to test the node's
missing-key behavior, fallback sentinel, schema and strict-mode semantics.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from workflowdirector.context import ContextNotFound


HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE / "nodes" / "universal_context_nodes.py"


class Output:
    def __init__(self, *args, ui=None):
        self.args = args
        self.ui = ui


class Registry:
    def __init__(self, result=(False, None), failure=None):
        self.result = result
        self.failure = failure
        self.calls = []

    def try_read_any(self, job, key):
        self.calls.append((job, key))
        if self.failure:
            raise self.failure
        return self.result


def get_class(registry):
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(
        x for x in module.body
        if isinstance(x, ast.ClassDef) and x.name == "ContextGetUniversal"
    )
    # Fixtures only evaluate the class itself; they do not run imports or
    # monkeypatch a real installed ComfyUI instance.
    fake_type = SimpleNamespace(
        Input=lambda name, **kw: (name, kw),
        Output=lambda **kw: ("output", kw),
    )
    fake_io = SimpleNamespace(
        ComfyNode=object,
        NodeOutput=Output,
        String=fake_type,
        Boolean=fake_type,
        AnyType=fake_type,
        Schema=lambda **kw: kw,
    )
    import logging
    scope = {
        "io": fake_io, "logging": logging,
        "get_context_registry": lambda: registry,
        "_job_id": lambda: "native-job-B",
        "ContextNotFound": ContextNotFound,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"),
         scope)
    return scope["ContextGetUniversal"]


class UniversalGetFallbackTests(unittest.TestCase):
    def test_schema_is_backward_compatible_and_strict_mode_optional(self):
        cls = get_class(Registry())
        schema = cls.define_schema()
        self.assertEqual(schema["node_id"], "WorkflowDirectorContextGetUniversal")
        self.assertEqual(schema["inputs"][0][0], "key")
        self.assertEqual(schema["inputs"][1][0], "error_if_missing")
        self.assertTrue(schema["inputs"][1][1]["optional"])
        self.assertFalse(schema["inputs"][1][1]["default"])
        self.assertEqual(len(schema["outputs"]), 1)

    def test_missing_key_returns_none_plus_visible_warning(self):
        reg = Registry()
        cls = get_class(reg)
        output = cls.execute("render1")
        self.assertEqual(reg.calls, [("native-job-B", "render1")])
        self.assertEqual(output.args, (None,))
        self.assertEqual(output.ui, {"text": ["WD_CONTEXT_MISSING:render1"]})

    def test_present_key_still_returns_original_value(self):
        image = {"image": [1, 2, 3]}
        reg = Registry((True, image))
        cls = get_class(reg)
        output = cls.execute("render1")
        self.assertEqual(output.args, (image,))
        self.assertIsNone(output.ui)

    def test_strict_mode_raises_on_genuine_absence(self):
        cls = get_class(Registry())
        with self.assertRaisesRegex(ContextNotFound, "render1"):
            cls.execute("render1", error_if_missing=True)

    def test_fallback_does_not_swallow_invalid_job_or_codec_errors(self):
        for failure in (RuntimeError("foreign job"), ValueError("codec corruption")):
            with self.subTest(failure=failure):
                cls = get_class(Registry(failure=failure))
                with self.assertRaises(type(failure)):
                    cls.execute("render1", error_if_missing=False)


if __name__ == "__main__":
    unittest.main()
