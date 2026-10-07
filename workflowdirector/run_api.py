"""Validation/building of a prepared run request.

Pure module: no ComfyUI imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import uuid

from .core import PreparedStep, RunPlan


class RunRequestError(ValueError):
    pass


def parse_run_request(payload: Mapping[str, Any]) -> tuple[RunPlan, str | None]:
    if not isinstance(payload, Mapping):
        raise RunRequestError("request body must be a JSON object")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise RunRequestError("steps must be a non-empty list")

    steps: list[PreparedStep] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, Mapping):
            raise RunRequestError(f"steps[{index}] must be an object")

        step_id = raw.get("step_id")
        workflow_id = raw.get("workflow_id")
        name = raw.get("name", f"Workflow {index + 1}")
        prompt = raw.get("prompt")
        workflow = raw.get("workflow")

        if not isinstance(step_id, str) or not step_id:
            raise RunRequestError(f"steps[{index}].step_id must be a non-empty string")
        if not isinstance(workflow_id, str) or not workflow_id:
            raise RunRequestError(
                f"steps[{index}].workflow_id must be a non-empty string"
            )
        if not isinstance(name, str):
            raise RunRequestError(f"steps[{index}].name must be a string")
        if not isinstance(prompt, Mapping):
            raise RunRequestError(f"steps[{index}].prompt must be an object")
        if not isinstance(workflow, Mapping):
            raise RunRequestError(f"steps[{index}].workflow must be an object")

        try:
            step = PreparedStep(
                step_id=step_id,
                workflow_id=workflow_id,
                name=name,
                prompt=prompt,
                workflow=workflow,
            )
        except (TypeError, ValueError) as exc:
            raise RunRequestError(
                f"steps[{index}] could not be prepared: {exc}"
            ) from exc

        steps.append(step)

    raw_run_id = payload.get("run_id")
    if raw_run_id is None:
        run_id = str(uuid.uuid4())
    elif isinstance(raw_run_id, str):
        try:
            run_id = str(uuid.UUID(raw_run_id))
        except ValueError as exc:
            raise RunRequestError("run_id must be a valid UUID") from exc
    else:
        raise RunRequestError("run_id must be a UUID string when provided")

    client_id = payload.get("client_id")
    if client_id is not None and not isinstance(client_id, str):
        raise RunRequestError("client_id must be a string or null")

    try:
        plan = RunPlan(
            run_id=run_id,
            steps=tuple(steps),
        )
    except ValueError as exc:
        raise RunRequestError(str(exc)) from exc

    return plan, client_id
