"""ComfyUI-WorkflowDirector custom node package.

The package targets the current stable ComfyUI release. Version-sensitive
behaviour is validated against the exact stable tag used by the lab.
"""

from comfy_api.latest import ComfyExtension

from .nodes.probe import WorkflowDirectorTestMarker
from .workflowdirector import VERSION as __version__

# Import registers the small diagnostic HTTP routes with ComfyUI.
from .workflowdirector import routes as _routes  # noqa: F401


class WorkflowDirectorExtension(ComfyExtension):
    async def get_node_list(self):
        return [
            WorkflowDirectorTestMarker,
        ]


async def comfy_entrypoint():
    return WorkflowDirectorExtension()


__all__ = ["comfy_entrypoint", "__version__"]
