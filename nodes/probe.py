"""Trivial output node used to validate installation and execution events."""

from __future__ import annotations

import logging

from ..workflowdirector.memory import compact_memory_line, memory_snapshot


class WorkflowDirectorTestMarker:
    """An intentionally boring output node for Phase 0/1 laboratory tests."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "label": (
                    "STRING",
                    {
                        "default": "WorkflowDirector test marker",
                        "multiline": False,
                    },
                ),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "mark"
    OUTPUT_NODE = True
    CATEGORY = "Workflow Director/Lab"

    def mark(self, label):
        snapshot = memory_snapshot()
        line = compact_memory_line(snapshot)
        logging.info("[WorkflowDirector] %s | %s", label, line)

        # A UI payload makes the node visibly confirm that it executed while the
        # console log gives us the exact instrumentation we need for the lab.
        return {
            "ui": {
                "text": [
                    f"{label}\n{line}",
                ]
            },
            "result": (),
        }
