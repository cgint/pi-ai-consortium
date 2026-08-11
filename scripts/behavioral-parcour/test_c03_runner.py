#!/usr/bin/env python3
"""Mechanical tests for the fresh c03 runner; never launches Pi."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c03_runner as c03


class C03RunnerTests(unittest.TestCase):
    def test_schedule_is_fresh_complete_and_ordered(self) -> None:
        self.assertEqual(len(c03.RUN_SPECS), 48)
        self.assertTrue(all(item["run_id"].startswith("c03-") for item in c03.RUN_SPECS))
        self.assertEqual([item["run_id"] for item in c03.RUN_SPECS[:4]], [
            "c03-off-r1-yaml-markdown", "c03-on-r1-yaml-markdown",
            "c03-off-r1-policy-retirement", "c03-on-r1-policy-retirement",
        ])

    def test_initial_and_per_cell_target_guards_have_distinct_scope(self) -> None:
        self.assertEqual(len(c03.run_target_paths(c03.RUN_SPECS)), 96)
        self.assertEqual(len(c03.run_target_paths([c03.RUN_SPECS[0]])), 2)

    def test_command_pins_executor_identity(self) -> None:
        command = c03.build_pi_command(Path("/abs/workspace"), Path("/abs/sessions"), "c03-off-r1-yaml-markdown")
        self.assertEqual(command[command.index("--provider") + 1], "8081-twins")
        self.assertEqual(command[command.index("--model") + 1], "qwen36-27b-nvidia-nvfp4")
        self.assertEqual(command[command.index("--thinking") + 1], "off")

    def test_child_environment_overrides_ambient_external_model(self) -> None:
        child = c03.build_child_env({"CONSORTIUM_MODEL": "google/gemini-3.5-flash", "KEEP": "yes"})
        self.assertEqual(child["CONSORTIUM_MODEL"], "8081-twins/qwen36-27b-nvidia-nvfp4")
        self.assertEqual(child["KEEP"], "yes")
        self.assertEqual(child["PI_SKIP_VERSION_CHECK"], "1")

    def test_review_timestamp_must_follow_freeze_and_not_be_future(self) -> None:
        self.assertTrue(c03.review_timing_is_valid("2026-08-11T18:00:00Z", "2026-08-11T18:01:00Z", "2026-08-11T18:02:00Z"))
        self.assertFalse(c03.review_timing_is_valid("2026-08-11T18:01:00Z", "2026-08-11T18:00:00Z", "2026-08-11T18:02:00Z"))
        self.assertFalse(c03.review_timing_is_valid("2026-08-11T18:00:00Z", "2026-08-11T18:03:00Z", "2026-08-11T18:02:00Z"))

    def test_guard_fire_includes_no_contribution_outcome(self) -> None:
        self.assertTrue(c03.guard_fired([{"type": "injection_skipped", "reason": "NO_CONTRIBUTION", "governor_reason": c03.GUARD_REASON}]))

    def test_continuity_requires_historical_marker(self) -> None:
        fixture = c03.FIXTURES["yaml-markdown"]
        self.assertTrue(c03.continuity_passes(fixture, "Markdown changelog entries current; YAML changelog entries superseded historical; RELEASE_STREAM=stable"))
        self.assertFalse(c03.continuity_passes(fixture, "Markdown changelog entries current; RELEASE_STREAM=stable"))


if __name__ == "__main__":
    unittest.main()
