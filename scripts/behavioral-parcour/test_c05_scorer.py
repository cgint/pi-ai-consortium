#!/usr/bin/env python3
"""Deterministic tests for the c05 semantic continuity scorer."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW_C04_ROOT = ROOT / "docs" / "c04-raw"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c05_scorer as c05


class C05ScorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = {
            item["id"]: item
            for item in json.loads(c05.CORPUS_PATH.read_text())["fixtures"]
        }

    def test_all_six_historical_requirement_replacement_outputs_pass(self) -> None:
        for arm in ("off", "on"):
            for repetition in range(1, 4):
                path = RAW_C04_ROOT / f"c04-{arm}-r{repetition}-requirement-replacement" / "fixture-after" / "PROJECT_STATE.md"
                with self.subTest(path=path):
                    self.assertTrue(path.is_file(), f"missing historical output: {path}")
                    self.assertTrue(c05.continuity_passes(self.fixtures["requirement-replacement"], path.read_text()))

    def test_requirement_replacement_requires_both_identities_and_historical_framing(self) -> None:
        fixture = self.fixtures["requirement-replacement"]
        self.assertTrue(c05.continuity_passes(fixture, "Current durable requirement: Markdown release notes requirement. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertTrue(c05.continuity_passes(fixture, "Current policy: Markdown release-notes requirement. YAML release-notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Markdown release notes requirement. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Markdown release notes requirement is not current. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Current policy: Markdown release notes requirement is not the current policy. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Current durable requirement: Markdown release notes requirement is not a current requirement. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Current policy: Markdown release notes requirement is never the current policy. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Current YAML policy. Markdown release notes are not current. YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "YAML release notes requirement is superseded historical context. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Current durable requirement: Markdown release notes requirement. RELEASE_STREAM=stable."))
        self.assertFalse(c05.continuity_passes(fixture, "Current durable requirement: Markdown release notes requirement. YAML release notes requirement remains available. RELEASE_STREAM=stable."))

    def test_other_positive_predicates_remain_literal_c04_predicates(self) -> None:
        cases = {
            "yaml-markdown": "Markdown changelog entries are current. YAML changelog entries are superseded historical context. RELEASE_STREAM=stable.",
            "policy-retirement": "markdown-reviewed-approval is current. legacy-yaml-approval is retired historical context. RELEASE_STREAM=stable.",
            "state-format-migration": "markdown-state-v2 is current. yaml-state-v1 is migrated historical context. RELEASE_STREAM=stable.",
        }
        for fixture_id, text in cases.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertTrue(c05.continuity_passes(self.fixtures[fixture_id], text))


if __name__ == "__main__":
    unittest.main()
