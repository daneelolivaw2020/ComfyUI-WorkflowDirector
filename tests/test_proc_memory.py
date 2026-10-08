"""Portable tests for Linux smaps_rollup parsing and graceful fallback."""

import unittest
from unittest.mock import patch

from workflowdirector.proc_memory import parse_smaps_rollup, process_smaps_rollup
from workflowdirector.memory_analysis import compare_snapshots


SAMPLE = """\
Rss:             2621440 kB
Pss:             2359296 kB
Pss_Anon:        2097152 kB
Pss_File:         245760 kB
Pss_Shmem:         16384 kB
Anonymous:       2097152 kB
Private_Dirty:   2117632 kB
Private_Clean:    368640 kB
Shared_Clean:      32768 kB
Swap:                 0 kB
IgnoredKernelField:  123 kB
"""


class SmapsTests(unittest.TestCase):
    def test_parses_in_gib_and_ignores_unknown_fields(self):
        result = parse_smaps_rollup(SAMPLE)
        self.assertEqual(result["rss_gib"], 2.5)
        self.assertEqual(result["pss_anon_gib"], 2.0)
        self.assertAlmostEqual(result["pss_file_gib"], 0.2344, places=4)
        self.assertAlmostEqual(result["pss_shmem_gib"], 0.0156, places=4)
        self.assertEqual(result["swap_gib"], 0)
        self.assertNotIn("IgnoredKernelField", result)

    def test_invalid_fields_and_unsupported_linux_are_safe(self):
        result = parse_smaps_rollup(
            "Pss_Anon: n/a kB\nPss_File: -100 kB\nRss: 100 KB\n"
        )
        self.assertEqual(result, {})
        with patch("workflowdirector.proc_memory.Path.read_text",
                   side_effect=FileNotFoundError):
            self.assertEqual(process_smaps_rollup(), {})
        self.assertEqual(process_smaps_rollup(pid=-1), {})

    def test_baseline_deltas_keep_anonymous_and_file_pss_separate(self):
        baseline = {
            "process_rss_gib": 2.0,
            "process_memory": {
                "pss_anon_gib": 1.3,
                "pss_file_gib": 0.5,
                "private_dirty_gib": 1.4,
            },
        }
        current = {
            "process_rss_gib": 2.0,
            "process_memory": {
                "pss_anon_gib": 1.5,
                "pss_file_gib": 0.3,
                "private_dirty_gib": 1.6,
            },
        }
        deltas = compare_snapshots(baseline, current)
        self.assertEqual(deltas["process_rss_gib"]["delta"], 0.0)
        self.assertEqual(deltas["process_pss_anon_gib"]["delta"], 0.2)
        self.assertEqual(deltas["process_pss_file_gib"]["delta"], -0.2)
        self.assertEqual(deltas["process_private_dirty_gib"]["delta"], 0.2)
