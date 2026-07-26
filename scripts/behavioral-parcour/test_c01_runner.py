#!/usr/bin/env python3
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import c01_runner as runner


class C01RunnerTests(unittest.TestCase):
    def test_frozen_prompts_checkpoint_schedules_and_run_ids(self):
        self.assertEqual(runner.CHECKPOINT_SCHEDULES["pre-stage-c"], ["A1", "D1", "A2", "D2", "A3", "D3"])
        self.assertEqual(runner.CHECKPOINT_SCHEDULES["post-stage-c"], ["A1", "D1", "A2", "D2", "A3", "D3"])
        self.assertEqual(runner.CHECKPOINT_SCHEDULES["post-stage-d"], ["A1", "A2", "D2", "A3"])
        self.assertEqual(runner.CHECKPOINT_SCHEDULES["post-stage-e"], ["A1", "A2", "D2", "A3"])
        self.assertEqual(runner.RUN_SPECS["post-stage-e"]["D2"]["run_id"], "c01-poststagee-d2-r2")
        self.assertEqual(len(runner.PROMPTS), 3)
        self.assertIn("replace the YAML changelog requirement with Markdown", runner.PROMPTS[1])

    def test_alias_map_covers_every_frozen_checkpoint_run_path(self):
        alias_path = runner.HERE / "alias-maps" / "c01-revision-continuity.json"
        literals = json.loads(alias_path.read_text())["literals"]
        for checkpoint in runner.CHECKPOINT_SCHEDULES:
            for spec in runner.RUN_SPECS[checkpoint].values():
                for prefix in ("/private/tmp", "/tmp"):
                    path = f"{prefix}/parcour-{spec['run_id']}/workspace"
                    self.assertEqual(literals.get(path), "/workspace", path)

    def test_command_has_exact_arm_extension_order_and_controls(self):
        workspace = Path("/tmp/example/workspace")
        sessions = Path("/tmp/example/sessions")
        active = runner.build_pi_command("x", 1, "active", workspace, sessions)
        disabled = runner.build_pi_command("x", 1, "disabled", workspace, sessions)
        active_ext = [active[i + 1] for i, value in enumerate(active) if value == "-e"]
        disabled_ext = [disabled[i + 1] for i, value in enumerate(disabled) if value == "-e"]
        self.assertEqual(active_ext, [str(runner.p.PROVIDER_EXT), str(runner.p.CONSORTIUM_EXT), str(runner.p.FOCUS_EXT)])
        self.assertEqual(disabled_ext, [str(runner.p.PROVIDER_EXT), str(runner.p.FOCUS_EXT)])
        for command in (active, disabled):
            self.assertIn("--no-extensions", command)
            self.assertIn("--dm-off", command)
            self.assertEqual(command[command.index("--thinking") + 1], "off")
            self.assertTrue(Path(command[command.index("--write-guard") + 1]).is_absolute())

    def test_sequencer_sends_only_frozen_turns_after_settle(self):
        seq = runner.C01Sequencer()
        self.assertEqual(seq.on_event({"type": "response", "id": "get_state", "success": True}), [])
        actions = seq.on_event({"type": "response", "id": "get_commands", "success": True})
        self.assertEqual(actions[0]["message"], runner.PROMPTS[0])
        for index in range(3):
            actions = seq.on_event({"type": "agent_settled"})
            if index < 2:
                self.assertEqual(actions[0]["message"], runner.PROMPTS[index + 1])
            else:
                self.assertEqual({a["id"] for a in actions}, {"state_final", "entries_final", "stats_final", "text_final"})

    def test_d1_zero_eligible_is_valid_per_run_fact(self):
        events = [{"type": "baseline_check", "baseline_available": False, "baseline_supplied": False}]
        check, facts = runner.d1_facts(events, "active")
        self.assertTrue(check.passed)
        self.assertEqual(facts["denominator"], 0)
        self.assertEqual(facts["numerator"], 0)

    def test_d2_capture_is_raw_only_with_explicit_unavailable_fields(self):
        events = [
            {"type": "deliberation_start", "_source_file": "x.jsonl", "_source_line": 1},
            {"type": "baseline_check", "baseline_available": False, "baseline_supplied": False, "_source_file": "x.jsonl", "_source_line": 2},
            {"type": "injection_skipped", "reason": "routine", "extractedContext": {"userRequirements": ["x"]}, "_source_file": "x.jsonl", "_source_line": 7},
            {"type": "deliberation_telemetry", "baseline_available": False, "baseline_supplied": False, "usage_status": "complete", "_source_file": "x.jsonl", "_source_line": 8},
        ]
        capture = runner.build_d2_capture(events, "active")
        self.assertEqual(capture["status"], "capture_only_unscored")
        observation = capture["observations"][0]
        self.assertFalse(observation["raw_extraction_model_text"]["available"])
        self.assertFalse(observation["exact_supplied_baseline_payload"]["available"])
        self.assertTrue(observation["parsed_extracted_context"]["available"])
        self.assertEqual(len(observation["parsed_extracted_context"]["sha256"]), 64)
        self.assertTrue(runner.validate_d2_capture(capture, "active").passed)
        keys = set()
        def collect(value):
            if isinstance(value, dict):
                keys.update(value)
                for child in value.values(): collect(child)
            elif isinstance(value, list):
                for child in value: collect(child)
        collect(capture)
        self.assertTrue(set(capture["prohibited_labels"]).isdisjoint(keys))
        incomplete = runner.build_d2_capture(events[:-1], "active")
        self.assertFalse(runner.validate_d2_capture(incomplete, "active").passed)

    def test_disabled_capture_is_explicit_not_applicable(self):
        capture = runner.build_d2_capture([], "disabled")
        self.assertEqual(capture, {"schema_version": "c01-d2-capture-v1", "status": "not_applicable_disabled_arm", "observations": []})
        self.assertTrue(runner.validate_d2_capture(capture, "disabled").passed)

    def test_fixture_and_final_text_mechanical_checks(self):
        completed = """# Release-note migration\nObjective: migrate the release-note workflow.\nCurrent: Markdown.\nCompatibility: RELEASE_STREAM=stable.\nHistorical: YAML superseded by the applied decision.\nStatus: applied.\n"""
        self.assertTrue(runner.validate_fixture(completed).passed)
        self.assertTrue(runner.validate_final_text("Markdown is current; RELEASE_STREAM=stable remains; YAML was superseded.").passed)
        stale = completed.replace("Historical: YAML superseded", "Current: YAML required")
        self.assertFalse(runner.validate_fixture(stale).passed)

    def test_path_diff_is_symmetric(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            shutil.copy2(runner.TEMPLATE_WORKSPACE / "PROJECT_STATE.md", workspace / "PROJECT_STATE.md")
            (workspace / "PROJECT_STATE.md").write_text("changed")
            self.assertTrue(runner.validate_path_diff(workspace).passed)
            (workspace / "extra.txt").write_text("extra")
            self.assertFalse(runner.validate_path_diff(workspace).passed)
            (workspace / "extra.txt").unlink()
            (workspace / "PROJECT_STATE.md").unlink()
            self.assertFalse(runner.validate_path_diff(workspace).passed)

    def test_well_formed_identity_mismatch_fails_before_any_target_path(self):
        spec = runner.CELL_SPECS["A1"]
        instance = runner.C01Runner("pre-stage-c", "A1", spec["run_id"], spec["arm"], spec["repetition"], "a" * 40, "b" * 40, "c" * 64, "d" * 64, "e" * 64, "f" * 40)
        result = instance.run()
        self.assertIn("Frozen identity mismatch before materialization", result["exception"])
        self.assertEqual(result["prompts_delivered"], 0)
        self.assertFalse(instance.tmp_root.exists())
        self.assertFalse(instance.evidence_dir.exists())

    def test_cell_not_in_checkpoint_schedule_fails_before_identity_resolution(self):
        instance = runner.C01Runner("post-stage-d", "D1", "c01-poststaged-d1-r1", "disabled", 1, "a" * 40, "b" * 40, "c" * 64, "d" * 64, "e" * 64, "f" * 40)
        with self.assertRaisesRegex(ValueError, "do not match frozen mapping"):
            instance._validate_frozen_inputs()
        self.assertFalse(instance.tmp_root.exists())

    def test_malformed_identity_fails_before_any_target_path(self):
        spec = runner.CELL_SPECS["A1"]
        instance = runner.C01Runner("pre-stage-c", "A1", spec["run_id"], spec["arm"], spec["repetition"], "bad", "b" * 40, "c" * 64, "d" * 64, "e" * 64, "f" * 40)
        self.assertFalse(instance.tmp_root.exists())
        result = instance.run()
        self.assertIn("Invalid addendum commit identity", result["exception"])
        self.assertEqual(result["prompts_delivered"], 0)
        self.assertFalse(instance.tmp_root.exists())
        self.assertFalse(instance.evidence_dir.exists())


if __name__ == "__main__":
    unittest.main()
