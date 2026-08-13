#!/usr/bin/env python3
"""Deterministic tests for the c05 Phase 0 probe; never launches Pi."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c05_phase0 as phase0
import c05_phase0_probe as probe


class C05Phase0ProbeTests(unittest.TestCase):
    def test_plan_is_confined_exact_and_prompt_free(self) -> None:
        plan = probe.build_plan({"CONSORTIUM_MODEL": "google/ambient"})
        self.assertEqual(plan["paths"]["workspace"], str(probe.WORKSPACE))
        self.assertEqual(plan["settings"]["path"], str(probe.WORKSPACE / ".pi" / "settings.json"))
        self.assertEqual(plan["settings"]["payload"], phase0.settings_spec(probe.WORKSPACE, True)[1])
        self.assertEqual(plan["child_environment"]["CONSORTIUM_MODEL"], phase0.MODEL_REF)
        self.assertTrue(all(plan["checks"].values()))
        self.assertEqual(plan["rpc_commands"], [
            {"id": "state_initial", "type": "get_state"},
            {"id": "state_final", "type": "get_state"},
        ])
        self.assertNotIn("prompt", json.dumps(plan["rpc_commands"]))

    def test_command_has_c04_extension_order_and_explicit_identity(self) -> None:
        command = probe.build_pi_command(probe.WORKSPACE, probe.SESSIONS)
        extensions = [command[index + 1] for index, value in enumerate(command) if value == "-e"]
        self.assertEqual(extensions, [str(probe.paths.PROVIDER_EXT), str(probe.paths.CONSORTIUM_EXT), str(probe.paths.FOCUS_EXT)])
        self.assertEqual(command[command.index("--provider") + 1], phase0.MODEL_PROVIDER)
        self.assertEqual(command[command.index("--model") + 1], phase0.MODEL_ID)
        self.assertEqual(command[command.index("--thinking") + 1], phase0.THINKING_LEVEL)
        self.assertEqual(command[command.index("--write-guard") + 1], str(probe.WORKSPACE))

    def test_plan_validation_makes_required_failures_fatal(self) -> None:
        plan = probe.build_plan({})
        plan["checks"]["zero_user_prompts"] = False
        self.assertEqual(probe.validate_plan(plan), ["zero_user_prompts"])
        self.assertEqual(probe.validate_plan({}), ["missing plan checks"])

    def test_dry_run_never_calls_live_execution(self) -> None:
        plan = probe.build_plan({})
        with patch.object(probe, "build_plan", return_value=plan), patch.object(probe, "run_live", side_effect=AssertionError("live execution")):
            with patch.object(sys, "argv", ["c05_phase0_probe.py", "--dry-run"]):
                self.assertEqual(probe.main(), 0)

    def test_path_confinement_rejects_external_paths(self) -> None:
        self.assertTrue(probe.confined(probe.WORKSPACE))
        self.assertFalse(probe.confined(Path("/tmp/c05-phase0-capability")))


if __name__ == "__main__":
    unittest.main()
