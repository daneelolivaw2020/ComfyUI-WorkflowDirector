"""Unit checks for nonintrusive external Comfy memory watcher."""

import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "memory_watch.py"
SPEC = importlib.util.spec_from_file_location("workflowdirector_memory_watch", PATH)
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class WatchTests(unittest.TestCase):
    def test_linux_smaps_metrics_and_units(self):
        raw = ("00400000-7fffffff ---p [rollup]\n"
               "Rss:              2048 kB\n"
               "Pss:              1024 kB\n"
               "Pss_Anon:          700 kB\n"
               "Pss_File:          300 kB\n"
               "Private_Dirty:     900 kB\n"
               "Swap:                2 kB\n"
               "VmFlags: rd ex mr\n")
        metrics = watch.parse_kib_fields(raw)
        self.assertEqual(metrics["rss_bytes"], 2048 * 1024)
        self.assertEqual(metrics["pss_bytes"], 1024 * 1024)
        self.assertEqual(metrics["pss_anon_bytes"], 700 * 1024)
        self.assertEqual(metrics["pss_file_bytes"], 300 * 1024)
        self.assertEqual(metrics["swap_bytes"], 2048)
        self.assertNotIn("VmFlags", metrics)

    def test_nvidia_smi_mib_and_malformed_rows(self):
        metrics = watch.parse_nvidia_csv(
            "0, 800 MiB, 15360 MiB\nN/A, unknown, xxx\n1, 200, 10000\n"
        )
        self.assertEqual(len(metrics), 2)
        self.assertEqual(metrics[0]["index"], 0)
        self.assertEqual(metrics[0]["used_bytes"], 800 * 2**20)
        self.assertEqual(metrics[1]["total_bytes"], 10000 * 2**20)

    def test_no_torch_import_or_cleanup_calls(self):
        source = PATH.read_text()
        self.assertNotIn("import torch", source)
        self.assertNotIn("unload_all_models", source)
        self.assertNotIn("empty_cache(", source)
        self.assertNotIn("/free", source)

    def test_identifies_only_requested_comfy_process(self):
        with patch.object(watch, "read_command", return_value=[
            "python", "/content/ComfyUI/main.py", "--port", "8188", "--cache-none",
        ]):
            self.assertTrue(watch.is_comfy_process(123, "8188"))
            self.assertFalse(watch.is_comfy_process(123, "8189"))
        with patch.object(watch, "read_command", return_value=[
            "python", "/content/unrelated/main.py", "--port", "8188",
        ]):
            self.assertFalse(watch.is_comfy_process(123, "8188"))


if __name__ == "__main__":
    unittest.main()
