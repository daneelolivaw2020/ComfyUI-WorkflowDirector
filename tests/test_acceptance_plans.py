"""Pure acceptance plan sanity tests (no Colab or Comfy required)."""

import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts" / "acceptance_probe.py"
spec = importlib.util.spec_from_file_location("wd_acceptance_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class AcceptancePlansTests(unittest.TestCase):
    def test_all_plans_use_two_distinct_jobs_and_workflow_ids(self):
        for case in ("string", "image", "latent", "failure"):
            with self.subTest(case=case):
                steps, expected = probe.plans(case)
                self.assertEqual(len(steps), 2)
                self.assertEqual([s["step_id"] for s in steps], ["A", "B"])
                self.assertNotEqual(steps[0]["workflow_id"], steps[1]["workflow_id"])
                self.assertTrue(all(isinstance(s["prompt"], dict) for s in steps))
                self.assertTrue(all("1" in s["prompt"] for s in steps))
                self.assertEqual(len(expected), 3)

    def test_string_consumer_observes_producer_not_a_hardcoded_value(self):
        steps, (_, kind, sentinel) = probe.plans("string")
        self.assertEqual(kind, "STRING")
        a, b = [s["prompt"] for s in steps]
        self.assertEqual(a["1"]["inputs"]["value"], sentinel)
        self.assertEqual(b["1"]["class_type"], "WorkflowDirectorContextGetString")
        self.assertEqual(b["2"]["inputs"]["label"], ["1", 0])
        self.assertNotIn(sentinel, str(b))

    def test_image_uses_native_output_node(self):
        steps, (_, kind, prefix) = probe.plans("image")
        self.assertEqual(kind, "IMAGE")
        a, b = [s["prompt"] for s in steps]
        self.assertEqual(a["1"]["class_type"], "EmptyImage")
        self.assertEqual(a["2"]["inputs"]["value"], ["1", 0])
        self.assertEqual(b["2"]["class_type"], "SaveImage")
        self.assertTrue(prefix.startswith("WD_Acceptance_IMAGE_"))

    def test_latent_plan_uses_native_empty_latent_and_save(self):
        steps, (_, kind, prefix) = probe.plans("latent")
        self.assertEqual(kind, "LATENT")
        a, b = [s["prompt"] for s in steps]
        self.assertEqual(a["1"]["class_type"], "EmptyLatentImage")
        self.assertEqual(a["2"]["inputs"]["value"], ["1", 0])
        self.assertEqual(b["2"]["class_type"], "SaveLatent")
        self.assertTrue(prefix.startswith("WD_Acceptance_LATENT_"))

    def test_failure_plan_only_validated_when_a_fails(self):
        steps, meta = probe.plans("failure")
        self.assertEqual(meta, (None, None, None))
        self.assertEqual(
            steps[0]["prompt"]["1"]["inputs"]["key"],
            "this.key.does.not.exist",
        )
        self.assertEqual(
            steps[1]["prompt"]["1"]["inputs"]["key"],
            "should.not.appear",
        )


if __name__ == "__main__":
    unittest.main()
