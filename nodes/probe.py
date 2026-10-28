"""Trivial V3 output node used to validate installation and execution."""

from __future__ import annotations

import logging

from comfy_api.latest import io

from ..workflowdirector.memory import compact_memory_line, memory_snapshot


class WorkflowDirectorTestMarker(io.ComfyNode):
    """An intentionally boring output node for Phase 0/1 laboratory tests."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="WorkflowDirectorTestMarker",
            display_name="WorkflowDirector · Test Marker",
            category="Workflow Director/Lab",
            inputs=[
                io.String.Input(
                    "label",
                    default="WorkflowDirector test marker",
                    multiline=False,
                )
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        """Force execution on every queue run so measurements are never cached."""

        return float("NaN")

    @classmethod
    def execute(cls, label) -> io.NodeOutput:
        snapshot = memory_snapshot()
        line = compact_memory_line(snapshot)
        logging.info("[WorkflowDirector] %s | %s", label, line)

        return io.NodeOutput(
            ui={
                "text": [
                    f"{label}\n{line}",
                ]
            }
        )
