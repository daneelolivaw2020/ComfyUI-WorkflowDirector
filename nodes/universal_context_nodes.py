"""Opt-in universal Context nodes using native ComfyUI v0.39 V3 sockets.

Existing six typed nodes are deliberately left untouched. "ANY" is a
connection capability, not permission to retain arbitrary Python objects.
"""

from __future__ import annotations

from comfy_api.latest import io

from .context_nodes import _job_id, _put
from ..workflowdirector.runtime import get_context_registry


class ContextPutUniversal(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.MatchType.Template("context_value")
        return io.Schema(
            node_id="WorkflowDirectorContextPutUniversal",
            display_name="PUT INTO CONTEXT (Universal)",
            is_experimental=True,
            category="Workflow Director/Context",
            description=(
                "Publish safe CPU-copyable values to run-scoped Context. "
                "The output matches the incoming socket type. "
                "Live model objects and unsupported custom classes fail safely."
            ),
            inputs=[
                io.String.Input("key", default="shared"),
                io.MatchType.Input("value", template=template),
            ],
            outputs=[
                io.MatchType.Output(template=template, display_name="value"),
            ],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key, value) -> io.NodeOutput:
        return _put(key, "VALUE", value)


class ContextGetUniversal(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorContextGetUniversal",
            display_name="GET FROM CONTEXT (Universal)",
            is_experimental=True,
            category="Workflow Director/Context",
            description=(
                "Read a previously committed Context key. Universal ANY output "
                "is checked by the consumer at runtime, not type-linked across "
                "independent workflow tabs."
            ),
            inputs=[io.String.Input("key", default="shared")],
            outputs=[io.AnyType.Output(display_name="value")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key) -> io.NodeOutput:
        return io.NodeOutput(get_context_registry().read_any(_job_id(), key))
