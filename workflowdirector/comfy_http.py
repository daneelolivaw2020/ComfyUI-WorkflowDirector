"""HTTP adapter for the native ComfyUI prompt/jobs APIs.

This module intentionally depends on HTTP contracts, not PromptQueue internals.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping
from urllib.parse import quote

import aiohttp

from .core import AdapterTransportError, JobState, SubmissionTransportError


class ComfyProtocolError(RuntimeError):
    """Comfy replied, but the response violated the expected API contract."""


class PromptRejectedError(RuntimeError):
    """Comfy rejected a prepared prompt before queueing it."""


class ComfyHttpAdapter:
    """Submit prepared prompts and observe native job state through HTTP."""

    _JOB_STATES = {
        "pending": JobState.PENDING,
        "in_progress": JobState.IN_PROGRESS,
        "completed": JobState.COMPLETED,
        "failed": JobState.FAILED,
        "cancelled": JobState.CANCELLED,
    }

    def __init__(
        self,
        *,
        base_url: str,
        session: aiohttp.ClientSession,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url cannot be empty")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be > 0")

        self._base_url = base_url.rstrip("/")
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)

    async def submit_prompt(
        self,
        *,
        prompt: Mapping[str, Any],
        workflow: Mapping[str, Any],
        prompt_id: str,
        client_id: str | None,
    ) -> str:
        body: dict[str, Any] = {
            "prompt_id": prompt_id,
            "prompt": prompt,
            "extra_data": {
                "comfy_usage_source": "workflowdirector",
                "extra_pnginfo": {
                    "workflow": workflow,
                },
            },
        }
        if client_id:
            body["client_id"] = client_id

        try:
            async with self._session.post(
                f"{self._base_url}/api/prompt",
                json=body,
                timeout=self._timeout,
            ) as response:
                payload = await self._read_json(response)

                if response.status != 200:
                    raise PromptRejectedError(
                        self._format_error(
                            "Comfy rejected prompt submission",
                            response.status,
                            payload,
                        )
                    )

        except PromptRejectedError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise SubmissionTransportError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

        acknowledged = payload.get("prompt_id")
        if not isinstance(acknowledged, str):
            raise ComfyProtocolError(
                "Prompt response did not contain a string prompt_id"
            )
        return acknowledged

    async def get_job_state(self, prompt_id: str) -> JobState:
        encoded = quote(prompt_id, safe="")

        try:
            async with self._session.get(
                f"{self._base_url}/api/jobs/{encoded}",
                timeout=self._timeout,
            ) as response:
                if response.status == 404:
                    await response.read()
                    return JobState.UNKNOWN

                payload = await self._read_json(response)
                if response.status != 200:
                    raise ComfyProtocolError(
                        self._format_error(
                            "Comfy job lookup failed",
                            response.status,
                            payload,
                        )
                    )

        except ComfyProtocolError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise AdapterTransportError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

        raw_state = payload.get("status")
        if not isinstance(raw_state, str):
            raise ComfyProtocolError(
                "Job response did not contain a string status"
            )

        try:
            return self._JOB_STATES[raw_state]
        except KeyError as exc:
            raise ComfyProtocolError(
                f"Unsupported Comfy job status: {raw_state!r}"
            ) from exc

    async def get_active_job_ids(self) -> set[str]:
        try:
            async with self._session.get(
                f"{self._base_url}/api/jobs?status=pending,in_progress&limit=100",
                timeout=self._timeout,
            ) as response:
                payload = await self._read_json(response)
                if response.status != 200:
                    raise ComfyProtocolError(
                        self._format_error(
                            "Comfy active-job lookup failed",
                            response.status,
                            payload,
                        )
                    )
        except ComfyProtocolError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise AdapterTransportError(
                f"{type(exc).__name__}: {exc}"
            ) from exc

        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ComfyProtocolError(
                "Active-job response did not contain a jobs list"
            )

        ids: set[str] = set()
        for job in jobs:
            if not isinstance(job, dict):
                raise ComfyProtocolError(
                    "Active-job response contained a non-object job"
                )
            job_id = job.get("id")
            status = job.get("status")
            if not isinstance(job_id, str) or not isinstance(status, str):
                raise ComfyProtocolError(
                    "Active-job entry is missing string id/status"
                )
            if status not in {"pending", "in_progress"}:
                raise ComfyProtocolError(
                    f"Active-job endpoint returned unexpected status {status!r}"
                )
            ids.add(job_id)

        return ids

    @staticmethod
    async def _read_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise
        except Exception as exc:
            text = await response.text()
            raise ComfyProtocolError(
                f"Expected JSON response, got {text[:500]!r}"
            ) from exc

        if not isinstance(payload, dict):
            raise ComfyProtocolError(
                f"Expected JSON object, got {type(payload).__name__}"
            )
        return payload

    @staticmethod
    def _format_error(prefix: str, status: int, payload: Mapping[str, Any]) -> str:
        return f"{prefix} (HTTP {status}): {dict(payload)!r}"
