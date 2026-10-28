# ComfyUI 0.39 / Colab T4 — acceptance runbook

Use the notebook at notebooks/WorkflowDirector_Colab_Acceptance_v0_39.ipynb in the **same runtime** containing your existing /content/ComfyUI installation. If it opens a new empty runtime, copy its cells to your current Colab notebook instead.

## Before testing

- Disable Auto Queue and confirm both native Jobs API and Director have no active jobs.
- Keep ComfyUI 0.39.0, the original launch flags, output directory, 127.0.0.1:8188, and --cache-none.
- Stop if the WorkflowDirector Git working tree has local edits. Save the original commit SHA to /content/workflowdirector_before_acceptance_commit.txt.
- Fetch feature/colab-acceptance; check out that revision in detached mode; restart only Comfy using the original process arguments.
- Do not rerun the old clean-install cells that delete /content/ComfyUI. Do not install Torch, GGUF or other model dependencies for these first tests.

## Test gates: start light, stop on unexpected failure

| Gate | Script argument | Expected result |
| --- | --- | --- |
| Preflight | --case preflight | Comfy v0.39.0, six Context nodes and helper nodes registered; cache-none detected |
| STRING | --case string | A and B jobs completed, STRING committed, B TestMarker receives unique sentinel |
| IMAGE | --case image | Both jobs complete, IMAGE committed, B saves uniquely named 96×64 PNG |
| LATENT | --case latent | Both jobs complete, LATENT committed, B saves uniquely named .latent file |
| Failure | --case failure | A fails on missing Context key; B never submitted; nothing committed |

The script is scripts/acceptance_probe.py. It uses the real Director HTTP endpoint, never downloads GGUF or invokes /free or destructive cleanup. Each step records evidence at /content/workflowdirector_acceptance_report.json. An HTTP 202 alone is not success: terminal status, separate native job IDs and real output/Context manifest matter. A deliberate failure gate returning PASS is expected.

Outputs are saved in ComfyUI's existing configured output directory, with unique test prefixes. The Colab notebook also supports ZIP export of logs and results. Inspect the ZIP before sharing, since logs may contain prompt text or local paths.

## Browser integration gate

Open workflows/context_string_A.json and context_string_B.json in separate topbar tabs. Link A and B using Capture current. Leave Refresh linked tabs before Run, Show executing workflow tab, and Notify on each workflow enabled. Edit A's STRING after capture, WITHOUT recapturing. Run A→B; verify B actually receives the new text, correct tab follows execution, both job statuses complete, and PSS columns populate. Close B and repeat: no job must be submitted; the UI should fail closed.

## Heavy gate — only after all above pass

Use the existing known-good A Klein Q4/Qwen Q4 and B Klein Q6/Qwen Q6, fixed seeds, same loaded models and launch flags. Add matching Context Put/Get IMAGE or LATENT nodes. Verify generated outputs, job IDs, logs, and end-of-boundary RSS/PSS/Torch/VRAM. These observations do not measure sampling peaks or prove indefinite stability.

## Rollback

Ensure no jobs are active. In the repository, checkout --detach the SHA in /content/workflowdirector_before_acceptance_commit.txt, then restart Comfy with the exact known-working command. No model files or outputs are removed.

## Known limits

Real Comfy V3 loading, frontend tabs and device-to-CPU copies require runtime acceptance. No full peak-memory recorder, disk scratch/checkpoints, or persistence after kernel death yet. Stacked development PRs remain unmerged into main.
