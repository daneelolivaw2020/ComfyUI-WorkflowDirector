# Model File Locations

WorkflowDirector does not create a separate model repository and does not change
normal ComfyUI model lookup.

Models remain in the normal ComfyUI model tree and are loaded by the normal
Comfy/custom-node loaders.

For current ComfyUI the relevant logical search groups include:

- diffusion models: models/unet and models/diffusion_models;
- text encoders: models/text_encoders and models/clip;
- VAE: models/vae;
- LoRA: models/loras.

ComfyUI-GGUF integrates with those existing search groups. Its diffusion loader
registers GGUF files against the current diffusion_models/unet paths, and its
GGUF CLIP loaders use the text_encoders/clip paths.

## Colab note

If ComfyUI itself lives under /content, then the normal paths naturally look
like:

    /content/ComfyUI/models/unet
    /content/ComfyUI/models/diffusion_models
    /content/ComfyUI/models/text_encoders
    /content/ComfyUI/models/vae
    /content/ComfyUI/models/loras

That is not a WorkflowDirector-specific layout.

If an existing notebook uses symlinks, extra_model_paths or mounted Drive to
make models visible in those logical locations, keep that setup for the first
baseline. Do not change storage location and memory architecture in the same
experiment.

A local-copy-vs-Drive comparison may later be used as a controlled diagnostic if
GGUF mmap/storage behaviour appears relevant.
