"""Unit tests for the native HTTP Comfy adapter."""

from __future__ import annotations

import json
import unittest

from workflowdirector.comfy_http import (
    ComfyHttpAdapter,
    ComfyProtocolError,
    PromptRejectedError,
)
from workflowdirector.core import JobState


class FakeResponse:
    def __init__(self, status, payload=None, text=None):
        self.status = status
        self._payload = payload
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def text(self):
        if self._text is not None:
            return self._text
        return json.dumps(self._payload)

    async def read(self):
        return (await self.text()).encode()


class FakeSession:
    def __init__(self):
        self.posts = []
        self.gets = []
        self.post_response = None
        self.get_response = None

    def post(self, url, *, json, timeout):
        self.posts.append((url, json, timeout))
        return self.post_response

    def get(self, url, *, timeout):
        self.gets.append((url, timeout))
        return self.get_response


class ComfyHttpAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_preserves_prompt_workflow_job_id_and_client_id(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            200,
            {"prompt_id": "11111111-1111-1111-1111-111111111111"},
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188/",
            session=session,
        )

        result = await adapter.submit_prompt(
            prompt={"1": {"class_type": "Test"}},
            workflow={"id": "wf", "nodes": []},
            prompt_id="11111111-1111-1111-1111-111111111111",
            client_id="browser-session",
        )

        self.assertEqual(result, "11111111-1111-1111-1111-111111111111")
        url, body, _ = session.posts[0]
        self.assertEqual(url, "http://127.0.0.1:8188/api/prompt")
        self.assertEqual(body["client_id"], "browser-session")
        self.assertEqual(
            body["extra_data"]["extra_pnginfo"]["workflow"]["id"],
            "wf",
        )
        self.assertEqual(
            body["extra_data"]["comfy_usage_source"],
            "workflowdirector",
        )

    async def test_submit_omits_empty_client_id(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            200,
            {"prompt_id": "11111111-1111-1111-1111-111111111111"},
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        await adapter.submit_prompt(
            prompt={},
            workflow={},
            prompt_id="11111111-1111-1111-1111-111111111111",
            client_id=None,
        )

        self.assertNotIn("client_id", session.posts[0][1])

    async def test_prompt_validation_error_is_not_transport_loss(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            400,
            {"error": {"type": "invalid_prompt"}},
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(PromptRejectedError):
            await adapter.submit_prompt(
                prompt={},
                workflow={},
                prompt_id="11111111-1111-1111-1111-111111111111",
                client_id=None,
            )

    async def test_job_404_maps_to_unknown(self):
        session = FakeSession()
        session.get_response = FakeResponse(404, {"error": "Job not found"})
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        state = await adapter.get_job_state(
            "11111111-1111-1111-1111-111111111111"
        )

        self.assertEqual(state, JobState.UNKNOWN)

    async def test_job_states_map_exactly(self):
        for raw, expected in {
            "pending": JobState.PENDING,
            "in_progress": JobState.IN_PROGRESS,
            "completed": JobState.COMPLETED,
            "failed": JobState.FAILED,
            "cancelled": JobState.CANCELLED,
        }.items():
            session = FakeSession()
            session.get_response = FakeResponse(200, {"status": raw})
            adapter = ComfyHttpAdapter(
                base_url="http://127.0.0.1:8188",
                session=session,
            )

            self.assertEqual(
                await adapter.get_job_state(
                    "11111111-1111-1111-1111-111111111111"
                ),
                expected,
            )

    async def test_unknown_native_status_is_protocol_error(self):
        session = FakeSession()
        session.get_response = FakeResponse(200, {"status": "mystery"})
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(ComfyProtocolError):
            await adapter.get_job_state(
                "11111111-1111-1111-1111-111111111111"
            )


if __name__ == "__main__":
    unittest.main()
