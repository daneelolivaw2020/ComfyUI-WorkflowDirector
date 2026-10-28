# WorkflowDirector lab workflows

`lab_smoke_A.json` and `lab_smoke_B.json` are deliberately trivial workflows
for the first real orchestration test.

They contain only `WorkflowDirectorTestMarker`, so they test:

- custom-node installation;
- frontend capture;
- RunPlan preparation;
- deterministic native job IDs;
- strict A -> boundary -> B sequencing;
- memory observation and run-status UI.

They do **not** test GGUF, LoRA, Context, model unloading or image generation.

After this smoke pair passes, use the user's existing known-working heavy
workflows as A and B. Do not add unload/free-memory nodes.
