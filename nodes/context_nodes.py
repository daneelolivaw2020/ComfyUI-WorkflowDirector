"""ComfyUI V3 nodes for run-scoped cross-workflow Context.

These nodes intentionally *do not* access the browser or a global Python
contextvar directly. ComfyUI v0.39.0 provides the real native prompt UUID
through get_executing_context(); the Director registered that UUID before
submitting the job. A manual Queue outside Director fails closed.
"""

from __future__ import annotations

from comfy_api.latest import io
from comfy_execution.utils import get_executing_context

from ..workflowdirector.context import ContextError
from ..workflowdirector.runtime import get_context_registry


def _job_id() -> str:
    context = get_executing_context()
    if context is None or not context.prompt_id:
        raise ContextError(
            "Context nodes require a running native ComfyUI prompt owned by WorkflowDirector"
        )
    return context.prompt_id


def _put(key: str, kind: str, value):
    get_context_registry().stage(_job_id(), key, kind, value)
    return io.NodeOutput(value)


def _get(key: str, kind: str):
    return io.NodeOutput(get_context_registry().read(_job_id(), key, kind))


class ContextPutString(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextPutString",
            display_name="Context Put · STRING",
            category="Workflow Director/Context",
            inputs=[
                io.String.Input("key", default="text", multiline=False),
                io.String.Input("value", default="", multiline=True),
            ],
            outputs=[io.String.Output()],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key, value) -> io.NodeOutput:
        return _put(key, "STRING", value)


class ContextGetString(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextGetString",
            display_name="Context Get · STRING",
            category="Workflow Director/Context",
            inputs=[io.String.Input("key", default="text", multiline=False)],
            outputs=[io.String.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key) -> io.NodeOutput:
        return _get(key, "STRING")


class ContextPutImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextPutImage",
            display_name="Context Put · IMAGE",
            category="Workflow Director/Context",
            inputs=[
                io.String.Input("key", default="image", multiline=False),
                io.Image.Input("value"),
            ],
            outputs=[io.Image.Output()],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key, value) -> io.NodeOutput:
        return _put(key, "IMAGE", value)


class ContextGetImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextGetImage",
            display_name="Context Get · IMAGE",
            category="Workflow Director/Context",
            inputs=[io.String.Input("key", default="image", multiline=False)],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key) -> io.NodeOutput:
        return _get(key, "IMAGE")


class ContextPutLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextPutLatent",
            display_name="Context Put · LATENT",
            category="Workflow Director/Context",
            inputs=[
                io.String.Input("key", default="latent", multiline=False),
                io.Latent.Input("value"),
            ],
            outputs=[io.Latent.Output()],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key, value) -> io.NodeOutput:
        return _put(key, "LATENT", value)


class ContextGetLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextGetLatent",
            display_name="Context Get · LATENT",
            category="Workflow Director/Context",
            inputs=[io.String.Input("key", default="latent", multiline=False)],
            outputs=[io.Latent.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key) -> io.NodeOutput:
        return _get(key, "LATENT")
