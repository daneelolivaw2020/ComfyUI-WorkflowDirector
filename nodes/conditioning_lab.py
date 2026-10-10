"""Small no-model CONDITIONING fixtures for genuine native V3 A->B testing.

Both nodes live only in Workflow Director/Lab. No CLIP, VAE, diffusion model,
CUDA context or weights are loaded by these fixtures.
"""

from __future__ import annotations

from comfy_api.latest import io


class WorkflowDirectorTestConditioningSource(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorTestConditioningSource",
            display_name="WorkflowDirector · Conditioning Source (Lab)",
            category="Workflow Director/Lab",
            inputs=[io.String.Input("label", default="CONDITIONING_TEST")],
            outputs=[io.Conditioning.Output(display_name="conditioning")],
        )

    @classmethod
    def execute(cls, label: str) -> io.NodeOutput:
        import torch

        embeddings = torch.arange(12, dtype=torch.float32).reshape(1, 3, 4)
        pooled = torch.tensor([[10.0, 20.0, 30.0, 40.0]])
        # Real Comfy CONDITIONING shape: list of [embedding, metadata].
        conditioning = [[embeddings, {
            "pooled_output": pooled,
            "wd_lab_label": label,
            "wd_lab_sequence": [1, 2, 3],
        }]]
        return io.NodeOutput(conditioning)


class _UnsafeControlReference:
    """Non-Tensor stand-in for a model-attached conditioning object."""
    pass


class WorkflowDirectorTestConditioningUnsafeSource(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorTestConditioningUnsafeSource",
            display_name="WorkflowDirector · Unsafe Conditioning (Lab)",
            category="Workflow Director/Lab",
            inputs=[],
            outputs=[io.Conditioning.Output(display_name="conditioning")],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        import torch

        # This is deliberately not a real ControlNet, to avoid downloading
        # or loading models just to exercise the fail-closed rule.
        embeddings = torch.arange(12, dtype=torch.float32).reshape(1, 3, 4)
        return io.NodeOutput([[embeddings, {
            "pooled_output": torch.ones((1, 4), dtype=torch.float32),
            "control": _UnsafeControlReference(),
        }]])


class WorkflowDirectorTestConditioningSink(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorTestConditioningSink",
            display_name="WorkflowDirector · Conditioning Sink (Lab)",
            category="Workflow Director/Lab",
            inputs=[
                io.Conditioning.Input("conditioning"),
                io.String.Input("expected_label", default="CONDITIONING_TEST"),
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, conditioning, expected_label: str) -> io.NodeOutput:
        import torch

        if not isinstance(conditioning, list) or len(conditioning) != 1:
            raise ValueError("Conditioning sink expected one conditioning segment")
        segment = conditioning[0]
        if not isinstance(segment, (list, tuple)) or len(segment) != 2:
            raise ValueError("Malformed Comfy CONDITIONING segment")
        embeddings, meta = segment
        if not isinstance(meta, dict):
            raise ValueError("Conditioning metadata is not a dict")
        if meta.get("wd_lab_label") != expected_label:
            raise ValueError("Wrong A->B conditioning sentinel")
        if meta.get("wd_lab_sequence") != [1, 2, 3]:
            raise ValueError("CONDITIONING metadata was corrupted in Context")
        expected_embeddings = torch.arange(
            12, dtype=torch.float32
        ).reshape(1, 3, 4)
        expected_pooled = torch.tensor([[10.0, 20.0, 30.0, 40.0]])
        if not torch.equal(embeddings.cpu(), expected_embeddings):
            raise ValueError("CONDITIONING embeddings changed in Context")
        if not isinstance(meta.get("pooled_output"), torch.Tensor):
            raise ValueError("Missing pooled_output tensor")
        if not torch.equal(meta["pooled_output"].cpu(), expected_pooled):
            raise ValueError("CONDITIONING pooled_output changed in Context")
        text = (
            f"PASS_CONDITIONING_TRANSFER_{expected_label}: "
            "embedding, pooled_output and metadata preserved"
        )
        return io.NodeOutput(ui={"text": [text]})
