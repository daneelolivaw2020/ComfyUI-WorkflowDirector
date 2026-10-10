"""Lab-only custom Comfy socket: prove Universal Context is not a name whitelist.

This socket name is intentionally absent from the Context codecs and typed
nodes. Its runtime payload uses independently copyable CPU tensors and plain
Python data. It is NOT an arbitrary opaque object transfer test.
"""

from __future__ import annotations

from comfy_api.latest import io


# A deliberately unfamiliar socket type. Neither Context PUT/GET nor their
# transport codec contains or needs this socket name.
MysteryPayload = io.Custom("WD_MYSTERY_BUNDLE_V1")


class WorkflowDirectorTestMysterySource(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorTestMysterySource",
            display_name="Mystery Bundle Source (Lab)",
            category="Workflow Director/Lab",
            inputs=[io.String.Input("label", default="MYSTERY_SENTINEL_01")],
            outputs=[MysteryPayload.Output(display_name="unknown_data")],
        )

    @classmethod
    def execute(cls, label: str) -> io.NodeOutput:
        import torch

        payload = {
            "label": label,
            "samples": torch.arange(12, dtype=torch.float32).reshape(3, 4),
            "parameters": {"threshold": 0.625, "enabled": True},
            "points": [11, 22, 33],
            "dimensions": (3, 4),
        }
        return io.NodeOutput(payload)


class WorkflowDirectorTestMysterySink(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorTestMysterySink",
            display_name="Mystery Bundle Verifier (Lab)",
            category="Workflow Director/Lab",
            inputs=[
                MysteryPayload.Input("unknown_data"),
                io.String.Input("expected_label", default="MYSTERY_SENTINEL_01"),
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, unknown_data, expected_label: str) -> io.NodeOutput:
        import torch

        if type(unknown_data) is not dict:
            raise ValueError("MYSTERY_CONTEXT: expected a plain dict")
        if unknown_data.get("label") != expected_label:
            raise ValueError("MYSTERY_CONTEXT: wrong cross-workflow label")
        if unknown_data.get("parameters") != {
            "threshold": 0.625, "enabled": True
        }:
            raise ValueError("MYSTERY_CONTEXT: parameters changed")
        if unknown_data.get("points") != [11, 22, 33]:
            raise ValueError("MYSTERY_CONTEXT: list changed")
        if unknown_data.get("dimensions") != (3, 4):
            raise ValueError("MYSTERY_CONTEXT: tuple changed")
        actual = unknown_data.get("samples")
        if type(actual) is not torch.Tensor:
            raise ValueError("MYSTERY_CONTEXT: tensor missing")
        expected = torch.arange(12, dtype=torch.float32).reshape(3, 4)
        if actual.device.type != "cpu" or not torch.equal(actual, expected):
            raise ValueError("MYSTERY_CONTEXT: tensor changed or not CPU")
        return io.NodeOutput(ui={
            "text": [f"PASS_MYSTERY_CONTEXT_{expected_label}"]
        })
