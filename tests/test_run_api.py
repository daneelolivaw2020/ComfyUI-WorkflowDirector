"""Unit tests for prepared run request parsing."""

from __future__ import annotations

import unittest
import uuid

from workflowdirector.run_api import RunRequestError, parse_run_request


def valid_payload():
    return {
        "steps": [
            {
                "step_id": "A",
                "workflow_id": "workflow-a",
                "name": "Workflow A",
                "prompt": {"1": {"class_type": "A"}},
                "workflow": {"id": "workflow-a", "nodes": []},
            },
            {
                "step_id": "B",
                "workflow_id": "workflow-b",
                "name": "Workflow B",
                "prompt": {"1": {"class_type": "B"}},
                "workflow": {"id": "workflow-b", "nodes": []},
            },
        ],
        "client_id": "browser",
    }


class RunRequestTests(unittest.TestCase):
    def test_generates_run_id_when_omitted(self):
        plan, client_id = parse_run_request(valid_payload())

        uuid.UUID(plan.run_id)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(client_id, "browser")

    def test_canonicalizes_supplied_uuid(self):
        run_id = str(uuid.uuid4()).upper()
        payload = valid_payload()
        payload["run_id"] = run_id

        plan, _ = parse_run_request(payload)

        self.assertEqual(plan.run_id, str(uuid.UUID(run_id)))

    def test_rejects_empty_steps(self):
        with self.assertRaises(RunRequestError):
            parse_run_request({"steps": []})

    def test_rejects_duplicate_step_ids(self):
        payload = valid_payload()
        payload["steps"][1]["step_id"] = "A"

        with self.assertRaises(RunRequestError):
            parse_run_request(payload)

    def test_rejects_missing_visual_workflow_snapshot(self):
        payload = valid_payload()
        del payload["steps"][0]["workflow"]

        with self.assertRaises(RunRequestError):
            parse_run_request(payload)

    def test_rejects_invalid_client_id_type(self):
        payload = valid_payload()
        payload["client_id"] = 123

        with self.assertRaises(RunRequestError):
            parse_run_request(payload)


if __name__ == "__main__":
    unittest.main()
