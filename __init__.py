"""ComfyUI-WorkflowDirector custom node package.

Phase 0 intentionally contains only instrumentation and a trivial lab output node.
The workflow-level director, Context, checkpoints, and memory barrier are added
only after the lower-level execution/memory assumptions are validated.
"""

from .nodes.probe import WorkflowDirectorTestMarker
from .workflowdirector import VERSION as __version__

# Import registers the small diagnostic HTTP routes with ComfyUI.
from .workflowdirector import routes as _routes  # noqa: F401

NODE_CLASS_MAPPINGS = {
    "WorkflowDirectorTestMarker": WorkflowDirectorTestMarker,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WorkflowDirectorTestMarker": "WorkflowDirector · Test Marker",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "__version__"]
