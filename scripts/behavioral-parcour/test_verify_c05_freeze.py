#!/usr/bin/env python3
"""Tests for the pre-commit-safe c05 freeze verifier; never launches Pi."""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_c05_freeze as verify


class VerifyC05FreezeTests(unittest.TestCase):
    def test_current_uncommitted_package_verifies(self):
        report = verify.verify()
        self.assertTrue(report["pass"])
        self.assertEqual(report["ledger"], {"runs": 56, "smoke": 8, "matrix": 48, "scheduled_runtime_targets_absent": True})
        self.assertEqual(report["phase0"]["result_sha256"], "f9a90f1a93f07f64d2da76602323906444d333ced4ccc20296439e3a537aa76f")
        self.assertTrue(report["package"]["controller_default_read_only"])
        self.assertEqual(report["package"]["runtime_version_policy"], {"pi": "0.84.*", "node": "22.*", "exact_strings_recorded": True})
        self.assertEqual(report["package"]["aggregate_thresholds"]["control_fires"], "0/24")

    def test_preregistration_verifies_patch_family_policy(self):
        report = verify.verify_preregistration_and_helpers()
        self.assertEqual(report["runtime_version_policy"], {"pi": "0.84.*", "node": "22.*", "exact_strings_recorded": True})

    def test_patch_compatibility_probe_is_zero_prompt_nested_identity_evidence(self):
        report = verify.verify_patch_compatibility_evidence()
        self.assertEqual(report["versions"], {"node": "v22.23.2", "pi": "0.84.2"})
        self.assertEqual(report["rpc_methods"], ["get_state", "get_state"])
        self.assertEqual(report["identity"], {"provider": "8081-twins", "model": "qwen36-27b-nvidia-nvfp4", "thinking": "off"})
        self.assertEqual(report["checks"], 13)

    def test_contract_excludes_its_self_and_all_mutable_publication_paths(self):
        data = json.loads(verify.CONTRACT.read_text())
        paths = {item["path"] for item in data["files"]}
        self.assertNotIn("scripts/behavioral-parcour/c05-contract-files.json", paths)
        self.assertNotIn("docs/c05-evidence/raw-publication-ledger.json", paths)
        self.assertFalse(any(path.startswith("docs/c05-raw/") or path.startswith("docs/c05-evidence/independent-review") for path in paths))

    def test_corpus_parity_accepts_only_separator_metadata(self):
        report = verify.verify_corpus_and_predicate()
        self.assertEqual(report["controls"], 4)
        corpus = json.loads(verify.C05_CORPUS.read_text())
        changed = copy.deepcopy(corpus)
        changed["fixtures"][0]["before"] += "changed"
        self.assertNotEqual(changed["fixtures"][0], json.loads(verify.C04_CORPUS.read_text())["fixtures"][0])


if __name__ == "__main__":
    unittest.main()
