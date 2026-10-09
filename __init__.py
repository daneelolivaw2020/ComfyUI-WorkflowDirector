"""ComfyUI-WorkflowDirector custom node package.

The package targets the current stable ComfyUI release. Version-sensitive
behaviour is validated against the exact stable tag used by the lab.
"""

from comfy_api.latest import ComfyExtension

from .nodes.probe import WorkflowDirectorTestMarker
from .nodes.context_nodes import (
    ContextPutString, ContextGetString,
    ContextPutImage, ContextGetImage,
    ContextPutLatent, ContextGetLatent,
)
from .nodes.universal_context_nodes import ContextPutUniversal, ContextGetUniversal
from .nodes.conditioning_lab import (
    WorkflowDirectorTestConditioningSource, WorkflowDirectorTestConditioningSink,
)
from .workflowdirector import VERSION as __version__

# ComfyUI v0.39.0 still discovers custom-node frontend extensions through
# WEB_DIRECTORY, including packages whose backend nodes use the V3 API.
WEB_DIRECTORY = "./web"

# Import registers the small diagnostic HTTP routes with ComfyUI.
from .workflowdirector import routes as _routes  # noqa: F401


class WorkflowDirectorExtension(ComfyExtension):
    async def get_node_list(self):
        return [
            WorkflowDirectorTestMarker,
            ContextPutString, ContextGetString,
            ContextPutImage, ContextGetImage,
            ContextPutLatent, ContextGetLatent,
            ContextPutUniversal, ContextGetUniversal,
            WorkflowDirectorTestConditioningSource, WorkflowDirectorTestConditioningSink,
        ]


async def comfy_entrypoint():
    return WorkflowDirectorExtension()


__all__ = ["WEB_DIRECTORY", "comfy_entrypoint", "__version__"]
