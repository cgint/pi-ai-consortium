#!/usr/bin/env python3
"""Mechanical tests for c04; never launches Pi."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c04_runner as c04


class C04RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.captured = json.loads(c04.STATE_FIXTURE_PATH.read_text())

    def test_captured_pi_0841_state_validates_nested_identity(self) -> None:
        result = c04.validate_executor_state(self.captured)
        self.assertTrue(result["pass"])
        self.assertEqual(result["observed"], {"provider": "8081-twins", "model": "qwen36-27b-nvidia-nvfp4", "thinking": "off"})

    def test_obsolete_top_level_identity_fields_do_not_pass(self) -> None:
        obsolete = {"success": True, "data": {"provider": "8081-twins", "modelId": "qwen36-27b-nvidia-nvfp4", "thinkingLevel": "off"}}
        self.assertFalse(c04.validate_executor_state(obsolete)["pass"])

    def test_missing_or_malformed_nested_identity_does_not_pass(self) -> None:
        missing = copy.deepcopy(self.captured); missing["data"].pop("model")
        malformed = copy.deepcopy(self.captured); malformed["data"]["model"] = "8081-twins/qwen36-27b-nvidia-nvfp4"
        wrong_thinking = copy.deepcopy(self.captured); wrong_thinking["data"]["thinkingLevel"] = "medium"
        self.assertFalse(c04.validate_executor_state(missing)["pass"])
        self.assertFalse(c04.validate_executor_state(malformed)["pass"])
        self.assertFalse(c04.validate_executor_state(wrong_thinking)["pass"])

    def test_fixture_provenance_hashes_the_byte_identical_capture(self) -> None:
        provenance = json.loads(c04.STATE_PROVENANCE_PATH.read_text())
        self.assertEqual(provenance["fixture_sha256"], c04.sha256_file(c04.STATE_FIXTURE_PATH))
        self.assertEqual(provenance["source_sha256"], provenance["fixture_sha256"])
        self.assertEqual(provenance["capture_runtime"], "Pi 0.84.1")
        self.assertIn("not c04 evidence", provenance["use_boundary"])

    def test_schedule_is_fresh_complete_and_ordered(self) -> None:
        self.assertEqual(len(c04.RUN_SPECS), 48)
        self.assertTrue(all(item["run_id"].startswith("c04-") for item in c04.RUN_SPECS))
        self.assertEqual([item["run_id"] for item in c04.RUN_SPECS[:4]], [
            "c04-off-r1-yaml-markdown", "c04-on-r1-yaml-markdown",
            "c04-off-r1-policy-retirement", "c04-on-r1-policy-retirement",
        ])

    def test_initial_and_per_cell_target_guards_have_distinct_scope(self) -> None:
        self.assertEqual(len(c04.run_target_paths(c04.RUN_SPECS)), 96)
        self.assertEqual(len(c04.run_target_paths([c04.RUN_SPECS[0]])), 2)

    def test_command_and_child_environment_pin_twins(self) -> None:
        command = c04.build_pi_command(Path("/abs/workspace"), Path("/abs/sessions"), "c04-off-r1-yaml-markdown")
        self.assertEqual(command[command.index("--provider") + 1], "8081-twins")
        self.assertEqual(command[command.index("--model") + 1], "qwen36-27b-nvidia-nvfp4")
        self.assertEqual(command[command.index("--thinking") + 1], "off")
        child = c04.build_child_env({"CONSORTIUM_MODEL": "google/gemini-3.5-flash"})
        self.assertEqual(child["CONSORTIUM_MODEL"], "8081-twins/qwen36-27b-nvidia-nvfp4")

    def test_review_timestamp_is_strictly_prospective(self) -> None:
        self.assertTrue(c04.review_timing_is_valid("2026-08-11T18:00:00Z", "2026-08-11T18:01:00Z", "2026-08-11T18:02:00Z"))
        self.assertFalse(c04.review_timing_is_valid("2026-08-11T18:01:00Z", "2026-08-11T18:00:00Z", "2026-08-11T18:02:00Z"))

    def test_guard_fire_includes_no_contribution_outcome(self) -> None:
        self.assertTrue(c04.guard_fired([{"type": "injection_skipped", "reason": "NO_CONTRIBUTION", "governor_reason": c04.GUARD_REASON}]))


if __name__ == "__main__":
    unittest.main()
