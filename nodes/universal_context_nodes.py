"""Opt-in universal Context nodes using native ComfyUI v0.39 V3 sockets.

Existing six typed nodes are deliberately left untouched. "ANY" is a
connection capability, not permission to retain arbitrary Python objects.
"""

from __future__ import annotations

import logging

from comfy_api.latest import io

from .context_nodes import _job_id, _put
from ..workflowdirector.context import ContextNotFound
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
                "Read a previously committed Context key. If unavailable, "
                "return None to let an Any Switch choose a fallback image or "
                "other value. Enable error_if_missing for strict execution."
            ),
            inputs=[
                io.String.Input("key", default="shared"),
                # Optional for backwards compatibility with saved workflows.
                # Missing Context should not prevent running B independently.
                io.Boolean.Input(
                    "error_if_missing", default=False, optional=True,
                    tooltip=(
                        "False (default): warn and return None for a fallback "
                        "switch. True: stop if this key is unavailable."
                    ),
                ),
            ],
            outputs=[io.AnyType.Output(display_name="value")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")

    @classmethod
    def execute(cls, key, error_if_missing=False) -> io.NodeOutput:
        found, value = get_context_registry().try_read_any(_job_id(), key)
        if found:
            return io.NodeOutput(value)

        if error_if_missing:
            raise ContextNotFound(
                f"Context key {key!r} is unavailable. Execute the producer "
                "workflow first, or disable 'error_if_missing' and connect "
                "a fallback to an Any Switch."
            )

        # Only a missing key / independent manual execution is recoverable:
        # invalid keys, abandoned jobs, foreign jobs and codec errors still
        # fail. None is intentionally recognized by rgthree Any Switch.
        logging.warning(
            "[WorkflowDirector] GET key %r unavailable: returning None. "
            "The downstream fallback switch may use its alternate input.",
            key,
        )
        return io.NodeOutput(
            None, ui={"text": [f"WD_CONTEXT_MISSING:{key}"]}
        )
