"""Unit and disposable-subprocess smoke tests for glibc diagnostic collector.

No ComfyUI import, torch import, GPU context, unload, or malloc_trim.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest
from unittest.mock import patch

from workflowdirector.allocator_diagnostics import (
    AllocatorDiagnosticsError,
    enabled,
    parse_malloc_info,
)

SAMPLE_XML = b"""\
<malloc version="1">
 <heap nr="0">
  <sizes />
  <total type="fast" count="1" size="11"/>
  <total type="rest" count="2" size="22"/>
  <system type="current" size="1000"/>
 </heap>
 <heap nr="1">
  <sizes />
  <total type="fast" count="3" size="33"/>
  <total type="rest" count="4" size="44"/>
  <system type="current" size="2000"/>
 </heap>
 <total type="fast" count="4" size="44"/>
 <total type="rest" count="6" size="66"/>
 <total type="mmap" count="2" size="512"/>
 <system type="current" size="3000"/>
 <system type="max" size="4000"/>
</malloc>
"""


class GlibcDiagnosticsTests(unittest.TestCase):
    def test_opt_in_off_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(enabled())
        with patch.dict(os.environ, {"WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS": "true"}):
            self.assertFalse(enabled())
        with patch.dict(os.environ, {"WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS": "1"}):
            self.assertTrue(enabled())

    def test_summary_uses_only_top_level_counters(self):
        result = parse_malloc_info(SAMPLE_XML)
        self.assertEqual(result["heap_entries"], 2)
        self.assertEqual(result["arena_system_current_bytes"], 3000)
        self.assertEqual(result["arena_system_max_bytes"], 4000)
        self.assertEqual(result["free_fast_bytes"], 44)
        self.assertEqual(result["free_rest_bytes"], 66)
        self.assertEqual(result["free_list_estimate_bytes"], 110)
        self.assertEqual(result["direct_mmap_bytes"], 512)
        self.assertEqual(result["direct_mmap_count"], 2)

    def test_rejects_malformed_xml_and_missing_fields(self):
        for bad in [b"", b"<not_malloc/>", b"<malloc><total type='rest' size='5'/></malloc>"]:
            with self.subTest(xml=bad):
                with self.assertRaises(AllocatorDiagnosticsError):
                    parse_malloc_info(bad)

    @unittest.skipUnless(platform.system() == "Linux", "glibc smoke runs only on Linux")
    def test_native_call_in_disposable_process(self):
        # C ABI safety: any error (including a crash) stays isolated to a
        # throwaway subprocess, not the ComfyUI PID or test runner process.
        probe = (
            "import json, os; "
            "from workflowdirector.allocator_diagnostics import capture_allocator; "
            "r = capture_allocator(); "
            "print(json.dumps({k:r[k] for k in "
            "('pid','heap_entries','arena_system_current_bytes','glibc_version')}))"
        )
        env = dict(os.environ)
        env.pop("WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS", None)
        p = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if p.returncode and ("glibc malloc_info unavailable" in p.stderr or
                             "glibc diagnostics require Linux" in p.stderr):
            self.skipTest("GNU libc not present")
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        obj = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertGreater(obj["pid"], 0)
        self.assertGreaterEqual(obj["heap_entries"], 1)
        self.assertGreaterEqual(obj["arena_system_current_bytes"], 0)
        self.assertTrue(obj["glibc_version"])

    def test_collector_never_calls_cleanup(self):
        path = Path(__file__).resolve().parents[1] / "workflowdirector" / "allocator_diagnostics.py"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("import torch", source)
        self.assertNotIn("malloc_trim(", source)
        self.assertNotIn("unload_all_models(", source)
        self.assertNotIn("empty_cache(", source)


if __name__ == "__main__":
    unittest.main()
