"""Unit tests for the native HTTP Comfy adapter."""

from __future__ import annotations

import json
import unittest

import aiohttp

from workflowdirector.comfy_http import (
    ComfyHttpAdapter,
    ComfyProtocolError,
    PromptRejectedError,
)
from workflowdirector.core import (
    AdapterTransportError,
    JobState,
    SubmissionTransportError,
)


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

    async def test_response_body_transport_loss_keeps_submission_ambiguous(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            200,
            aiohttp.ClientPayloadError("simulated truncated response"),
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(SubmissionTransportError):
            await adapter.submit_prompt(
                prompt={},
                workflow={},
                prompt_id="11111111-1111-1111-1111-111111111111",
                client_id=None,
            )

    async def test_http_200_without_prompt_id_is_ambiguous_submission(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            200,
            {"number": 1},
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(SubmissionTransportError):
            await adapter.submit_prompt(
                prompt={},
                workflow={},
                prompt_id="11111111-1111-1111-1111-111111111111",
                client_id=None,
            )

    async def test_http_200_invalid_json_is_ambiguous_submission(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            200,
            ValueError("simulated invalid json"),
            text="<truncated>",
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(SubmissionTransportError):
            await adapter.submit_prompt(
                prompt={},
                workflow={},
                prompt_id="11111111-1111-1111-1111-111111111111",
                client_id=None,
            )

    async def test_http_400_invalid_json_is_still_a_rejection(self):
        session = FakeSession()
        session.post_response = FakeResponse(
            400,
            ValueError("simulated invalid json"),
            text="<bad request body unavailable>",
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

    async def test_job_response_body_transport_loss_is_retryable_transport_error(self):
        session = FakeSession()
        session.get_response = FakeResponse(
            200,
            aiohttp.ClientPayloadError("simulated truncated response"),
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(AdapterTransportError):
            await adapter.get_job_state(
                "11111111-1111-1111-1111-111111111111"
            )

    async def test_active_jobs_returns_pending_and_in_progress_ids(self):
        session = FakeSession()
        session.get_response = FakeResponse(
            200,
            {
                "jobs": [
                    {"id": "job-a", "status": "pending"},
                    {"id": "job-b", "status": "in_progress"},
                ]
            },
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        ids = await adapter.get_active_job_ids()

        self.assertEqual(ids, {"job-a", "job-b"})
        self.assertIn(
            "status=pending,in_progress",
            session.gets[0][0],
        )

    async def test_active_jobs_rejects_unexpected_status(self):
        session = FakeSession()
        session.get_response = FakeResponse(
            200,
            {"jobs": [{"id": "job-a", "status": "completed"}]},
        )
        adapter = ComfyHttpAdapter(
            base_url="http://127.0.0.1:8188",
            session=session,
        )

        with self.assertRaises(ComfyProtocolError):
            await adapter.get_active_job_ids()

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
