"""Sanity-check the opt-in visual lab example workflows without Comfy imports."""

import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parents[1] / "workflows"


class UniversalVisualWorkflowFilesTests(unittest.TestCase):
    def test_linked_conditioning_examples(self):
        a = json.loads((HERE / "universal_conditioning_A.json").read_text())
        b = json.loads((HERE / "universal_conditioning_B.json").read_text())
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(len(a["nodes"]), 2)
        self.assertEqual(len(b["nodes"]), 2)
        self.assertEqual([n["type"] for n in a["nodes"]], [
            "WorkflowDirectorTestConditioningSource",
            "WorkflowDirectorContextPutUniversal",
        ])
        self.assertEqual([n["type"] for n in b["nodes"]], [
            "WorkflowDirectorContextGetUniversal",
            "WorkflowDirectorTestConditioningSink",
        ])
        self.assertEqual(a["nodes"][1]["widgets_values"][0],
                         b["nodes"][0]["widgets_values"][0])
        self.assertEqual(a["nodes"][0]["widgets_values"][0],
                         b["nodes"][1]["widgets_values"][0])
        for graph in (a, b):
            self.assertEqual(len(graph["links"]), 1)
            link_id, source, source_slot, dest, dest_slot, link_type = graph["links"][0]
            self.assertEqual(link_type, "CONDITIONING")
            nodes = {node["id"]: node for node in graph["nodes"]}
            self.assertEqual(nodes[source]["outputs"][source_slot]["links"], [link_id])
            self.assertEqual(nodes[dest]["inputs"][dest_slot]["link"], link_id)
            self.assertEqual(graph["last_node_id"], max(nodes))
            self.assertEqual(graph["last_link_id"], link_id)


if __name__ == "__main__":
    unittest.main()
