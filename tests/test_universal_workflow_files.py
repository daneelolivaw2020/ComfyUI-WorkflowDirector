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


    def test_linked_image_examples_match_native_socket_schema(self):
        a = json.loads((HERE / "universal_image_A.json").read_text())
        b = json.loads((HERE / "universal_image_B.json").read_text())
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual([n["type"] for n in a["nodes"]], [
            "EmptyImage", "WorkflowDirectorContextPutUniversal",
        ])
        self.assertEqual([n["type"] for n in b["nodes"]], [
            "WorkflowDirectorContextGetUniversal", "SaveImage",
        ])
        self.assertEqual(a["nodes"][0]["widgets_values"], [96, 64, 1, 3116139])
        self.assertEqual(
            a["nodes"][1]["widgets_values"], b["nodes"][0]["widgets_values"]
        )
        self.assertEqual(a["nodes"][1]["widgets_values"], ["demo.image"])
        self.assertEqual(a["nodes"][1]["inputs"][0]["type"],
                         "COMFY_MATCHTYPE_V3")
        self.assertEqual(b["nodes"][0]["outputs"][0]["type"], "*")
        for graph in (a, b):
            self.assertEqual(len(graph["links"]), 1)
            link_id, source, source_slot, dest, dest_slot, link_type = graph["links"][0]
            self.assertEqual(link_type, "IMAGE")
            nodes = {node["id"]: node for node in graph["nodes"]}
            self.assertEqual(nodes[source]["outputs"][source_slot]["links"], [link_id])
            self.assertEqual(nodes[dest]["inputs"][dest_slot]["link"], link_id)
            self.assertEqual(graph["last_node_id"], max(nodes))
            self.assertEqual(graph["last_link_id"], link_id)


    def test_unknown_socket_transfer_needs_no_type_specific_put_get(self):
        a = json.loads((HERE / "universal_unknown_socket_A.json").read_text())
        b = json.loads((HERE / "universal_unknown_socket_B.json").read_text())
        custom_socket = "WD_MYSTERY_BUNDLE_V1"
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual([n["type"] for n in a["nodes"]], [
            "WorkflowDirectorTestMysterySource",
            "WorkflowDirectorContextPutUniversal",
        ])
        self.assertEqual([n["type"] for n in b["nodes"]], [
            "WorkflowDirectorContextGetUniversal",
            "WorkflowDirectorTestMysterySink",
        ])
        self.assertEqual(a["nodes"][0]["outputs"][0]["type"], custom_socket)
        self.assertEqual(b["nodes"][1]["inputs"][0]["type"], custom_socket)
        self.assertEqual(a["nodes"][1]["inputs"][0]["type"],
                         "COMFY_MATCHTYPE_V3")
        self.assertEqual(b["nodes"][0]["outputs"][0]["type"], "*")
        self.assertEqual(a["nodes"][1]["widgets_values"], ["demo.mystery"])
        self.assertEqual(a["nodes"][1]["widgets_values"],
                         b["nodes"][0]["widgets_values"])
        self.assertEqual(a["nodes"][0]["widgets_values"],
                         b["nodes"][1]["widgets_values"])
        for workflow in (a, b):
            self.assertEqual(workflow["links"][0][5], custom_socket)
            nodes = {n["id"]: n for n in workflow["nodes"]}
            _, source, source_slot, dest, dest_slot, _ = workflow["links"][0]
            self.assertEqual(nodes[source]["outputs"][source_slot]["links"], [1])
            self.assertEqual(nodes[dest]["inputs"][dest_slot]["link"], 1)

    def test_cleanup_example_runs_independent_native_chain_without_context(self):
        c = json.loads((HERE / "cleanup_between_A_B_C.json").read_text())
        kinds = [n["type"] for n in c["nodes"]]
        self.assertEqual(
            kinds, ["EmptyImage", "MemoryStatus", "MemoryManager",
                    "RAMCleanup", "SaveImage"],
        )
        self.assertFalse(any("Context" in kind for kind in kinds))
        self.assertEqual(c["last_node_id"], 5)
        self.assertEqual(c["last_link_id"], 4)
        self.assertEqual(len(c["links"]), 4)
        nodes = {node["id"]: node for node in c["nodes"]}
        for link_id, origin, output_slot, target, input_slot, _ in c["links"]:
            self.assertEqual(nodes[origin]["outputs"][output_slot]["links"], [link_id])
            self.assertEqual(nodes[target]["inputs"][input_slot]["link"], link_id)
        self.assertEqual(nodes[3]["widgets_values"], [True] * 5)
        self.assertEqual(nodes[4]["widgets_values"], [True, True, True, 3])


if __name__ == "__main__":
    unittest.main()
