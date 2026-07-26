#!/usr/bin/env python3
import copy
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import c01_d5_scorer as scorer


TRANSCRIPT = [
    {"role": "user", "content": [{"type": "text", "text": "Use FORMAT_NEW"}]},
    {"role": "additional_context", "content": [{"type": "text", "text": "Use FORMAT_NEW"}]},
    {"role": "assistant", "content": [{"type": "text", "text": "Using FORMAT_NEW"}]},
]


def output(status="scored"):
    return {
        "schema_version": "c01-d5-v1",
        "bundle_id": "T001",
        "status": status,
        "unearned_interruptions": [] if status == "unscorable" else [{
            "category": "restates_explicit_current_requirement",
            "event_index": 2,
            "evidence_message_indexes": [1, 2],
            "reason": "Repeats the explicit requirement.",
        }],
        "missed_interventions": [],
        "ambiguity_reasons": ["Insufficient evidence"] if status == "unscorable" else [],
    }


def record(number, value, valid=True):
    return {
        "pass": number,
        "valid": valid,
        "validation_error": None if valid else "bad",
        "parsed": value,
        "normalized_labels": scorer.normalize_output(value) if valid and value["status"] == "scored" else [],
    }


class D5ScorerTests(unittest.TestCase):
    def test_closed_schema_and_event_roles(self):
        value = output()
        self.assertEqual(scorer.validate_output(value, "T001", TRANSCRIPT), (True, "valid"))
        bad = copy.deepcopy(value)
        bad["extra"] = True
        self.assertFalse(scorer.validate_output(bad, "T001", TRANSCRIPT)[0])
        bad = copy.deepcopy(value)
        bad["unearned_interruptions"][0]["event_index"] = 3
        self.assertFalse(scorer.validate_output(bad, "T001", TRANSCRIPT)[0])

    def test_unscorable_has_no_labels_and_requires_reason(self):
        value = output("unscorable")
        self.assertTrue(scorer.validate_output(value, "T001", TRANSCRIPT)[0])
        value["ambiguity_reasons"] = []
        self.assertFalse(scorer.validate_output(value, "T001", TRANSCRIPT)[0])

    def test_unanimous_semantic_labels_ignore_reason_and_valid_citation_variance(self):
        values = [output() for _ in range(3)]
        values[1]["unearned_interruptions"][0]["reason"] = "Different wording."
        values[2]["unearned_interruptions"][0]["evidence_message_indexes"] = [1, 2, 3]
        records = [record(i + 1, value) for i, value in enumerate(values)]
        aggregate = scorer.aggregate_passes(records)
        self.assertEqual(aggregate["status"], "scored")
        self.assertEqual(aggregate["normalized_labels"], [["unearned", "restates_explicit_current_requirement", 2]])

    def test_disagreement_invalid_and_evaluator_unscorable_never_majority(self):
        values = [output() for _ in range(3)]
        values[2]["unearned_interruptions"] = []
        disagreement = scorer.aggregate_passes([record(i + 1, v) for i, v in enumerate(values)])
        self.assertEqual(disagreement["status"], "unscorable")
        invalid = scorer.aggregate_passes([record(1, output()), record(2, output(), False), record(3, output())])
        self.assertEqual(invalid["status"], "unscorable")
        ambiguous = scorer.aggregate_passes([record(1, output()), record(2, output("unscorable")), record(3, output())])
        self.assertEqual(ambiguous["status"], "unscorable")

    def test_rubric_freezes_episode_counting_and_label_event_evidence(self):
        rubric = scorer.DEFAULT_RUBRIC.read_text()
        self.assertIn("one missed intervention per uninterrupted category-specific divergence episode", rubric)
        self.assertIn("Use the final uncorrected assistant event", rubric)
        self.assertIn("labelled additional_context event_index", rubric)

    def test_command_is_tool_free_fresh_and_pinned(self):
        command = scorer.build_command(Path("/provider.ts"), "rubric", "prompt")
        joined = " ".join(command)
        for required in ("--no-tools", "--no-session", "--no-extensions", "--no-context-files", "--thinking off"):
            self.assertIn(required, joined)
        self.assertIn("qwen36-27b-nvidia-nvfp4", command)
        self.assertNotIn("--arm", command)

    def test_identity_failure_precedes_output_creation(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "never-created"
            rc = scorer.main([
                "--bundle", str(Path(td) / "missing.jsonl"),
                "--gate", str(Path(td) / "missing.gate.json"),
                "--bundle-id", "T001",
                "--out-dir", str(out),
                "--rubric-sha256", "bad",
                "--scorer-sha256", "bad",
            ])
            self.assertEqual(rc, 2)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
