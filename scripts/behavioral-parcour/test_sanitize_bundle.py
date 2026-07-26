#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sanitize_bundle as sb


class SanitizeBundleTests(unittest.TestCase):
    def test_observed_custom_envelope_becomes_neutral_context(self):
        entry = {
            "type": "custom",
            "customType": "pi-ai-consortium",
            "data": {"kind": "deliberation", "synthesis": "WARN useful guidance", "probe_count": 5},
        }
        self.assertEqual(
            sb.sanitize_custom(entry),
            {"role": "additional_context", "content": [{"type": "text", "text": "WARN useful guidance"}]},
        )

    def test_unrelated_or_malformed_custom_envelopes_are_dropped(self):
        cases = [
            {"type": "custom", "customType": "other", "data": {"kind": "deliberation", "synthesis": "x"}},
            {"type": "custom", "customType": "pi-ai-consortium", "data": {"kind": "other", "synthesis": "x"}},
            {"type": "custom", "customType": "pi-ai-consortium", "data": {"kind": "deliberation"}},
            {"type": "custom_message", "customType": "pi-ai-consortium", "data": {"kind": "deliberation", "synthesis": "x"}},
            {"type": "custom", "text": "legacy path must not survive"},
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertIsNone(sb.sanitize_custom(case))

    def test_deny_list_hit_writes_only_quarantined_bundle(self):
        root = Path(__file__).resolve().parent
        alias = root / "alias-maps" / "c01-revision-continuity.json"
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.jsonl"
            raw.write_text('{"type":"message","message":{"role":"user","content":[{"type":"text","text":"provider is olla"}]}}\n')
            out = Path(td) / "scoring"
            import subprocess
            completed = subprocess.run(
                [sys.executable, str(root / "sanitize_bundle.py"), "--session", str(raw),
                 "--alias-map", str(alias), "--bundle-id", "Q001", "--out-dir", str(out)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 3)
            self.assertTrue((out / "Q001.jsonl.QUARANTINED").exists())
            self.assertFalse((out / "Q001.jsonl").exists())
            self.assertFalse(json.loads((out / "Q001.gate.json").read_text())["clean"])

    def test_c01_synthetic_bundle_keeps_guidance_and_strips_provenance(self):
        root = Path(__file__).resolve().parent
        raw = root / "c01-fixtures" / "unearned.session.jsonl"
        alias = root / "alias-maps" / "c01-revision-continuity.json"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scoring"
            # Exercise the CLI because output placement and deny-list behavior are part of the contract.
            import subprocess
            completed = subprocess.run(
                [sys.executable, str(root / "sanitize_bundle.py"), "--session", str(raw),
                 "--alias-map", str(alias), "--bundle-id", "T001", "--out-dir", str(out),
                 "--arm", "synthetic"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            body = (out / "T001.jsonl").read_text()
            self.assertIn('"role":"additional_context"', body)
            self.assertIn("FORMAT_NEW", body)
            self.assertNotIn("pi-ai-consortium", body)
            gate = json.loads((out / "T001.gate.json").read_text())
            self.assertTrue(gate["clean"])
            self.assertEqual(gate["alias_map"]["id"], "c01-revision-continuity")


if __name__ == "__main__":
    unittest.main()
