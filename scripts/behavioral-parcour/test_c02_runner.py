#!/usr/bin/env python3
"""Mechanical tests for the c02 fresh supersession runner; no Pi subprocesses."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c02_runner as c02


class C02RunnerTests(unittest.TestCase):
    def test_frozen_schedule_has_all_pairs_and_repetitions(self) -> None:
        self.assertEqual(len(c02.RUN_SPECS), 48)
        self.assertEqual([item["run_id"] for item in c02.RUN_SPECS[:6]], [
            "c02-off-r1-yaml-markdown", "c02-on-r1-yaml-markdown",
            "c02-off-r1-policy-retirement", "c02-on-r1-policy-retirement",
            "c02-off-r1-requirement-replacement", "c02-on-r1-requirement-replacement",
        ])
        self.assertEqual({item["repetition"] for item in c02.RUN_SPECS}, {1, 2, 3})
        self.assertEqual({item["arm"] for item in c02.RUN_SPECS}, {"off", "on"})

    def test_positive_predicate_requires_current_and_historical_markers(self) -> None:
        fixture = c02.FIXTURES["yaml-markdown"]
        passing = "Markdown changelog entries are current. YAML changelog entries are superseded historical context. RELEASE_STREAM=stable."
        failing = "Markdown changelog entries are current. RELEASE_STREAM=stable."
        self.assertTrue(c02.continuity_passes(fixture, passing))
        self.assertFalse(c02.continuity_passes(fixture, failing))

    def test_guard_reason_is_exact_for_complete_and_no_contribution_events(self) -> None:
        events = [
            {"type": "injection_complete", "governor_reason": "Explicit durable-state supersession guard"},
            {"type": "injection_skipped", "reason": "NO_CONTRIBUTION", "governor_reason": "Explicit durable-state supersession guard"},
            {"type": "injection_complete", "governor_reason": "Context extraction identified active gaps"},
        ]
        self.assertTrue(c02.guard_fired(events[:1]))
        self.assertTrue(c02.guard_fired(events[1:2]))
        self.assertFalse(c02.guard_fired(events[2:]))

    def test_arm_guard_setting_is_derived_without_workspace(self) -> None:
        self.assertFalse(c02.arm_guard_enabled({"arm": "off"}))
        self.assertTrue(c02.arm_guard_enabled({"arm": "on"}))


if __name__ == "__main__":
    unittest.main()
