#!/usr/bin/env python3
"""Deterministic c05 Phase 0 tests; never launches Pi or sends a prompt."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c05_phase0 as phase0

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMP_ROOT = REPO_ROOT / ".parcour-runs"


def repository_tempdir() -> tempfile.TemporaryDirectory[str]:
    """Create an automatically cleaned c05 test directory inside the repository."""
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TEMP_ROOT, prefix="c05-phase0-")


class C05Phase0Tests(unittest.TestCase):
    def test_versions_are_provenance_under_compatible_policy(self) -> None:
        result = phase0.version_provenance("v22.23.2\n", "0.84.1\n")
        self.assertTrue(result["pass"])
        self.assertEqual(result["observed"], {"node": "v22.23.2", "pi": "0.84.1"})
        self.assertTrue(phase0.version_provenance("v23.0.0", "0.90.0")["pass"])
        self.assertTrue(phase0.version_provenance("v22.0.0", "0.74.0")["pass"])
        self.assertFalse(phase0.version_provenance("v21.9.0", "0.73.9")["pass"])
        self.assertFalse(phase0.version_provenance("v22.23", "unknown")["pass"])

    def test_extensions_must_exist_and_match_sha256(self) -> None:
        with repository_tempdir() as temp:
            extension = Path(temp) / "extension.ts"
            extension.write_text("export {};\n")
            digest = hashlib.sha256(extension.read_bytes()).hexdigest()
            self.assertTrue(phase0.validate_extensions({extension: digest})["pass"])
            self.assertFalse(phase0.validate_extensions({extension: "0" * 64})["pass"])
            self.assertFalse(phase0.validate_extensions({Path(temp) / "missing.ts": digest})["pass"])

    def test_child_model_explicitly_overrides_ambient_value(self) -> None:
        ambient = {"CONSORTIUM_MODEL": "ambient/provider", "KEEP": "yes"}
        child = phase0.build_child_env(ambient)
        self.assertEqual(child["CONSORTIUM_MODEL"], phase0.MODEL_REF)
        self.assertEqual(child["KEEP"], "yes")
        self.assertTrue(phase0.validate_child_env(child, ambient))
        self.assertTrue(phase0.validate_child_env({"CONSORTIUM_MODEL": phase0.MODEL_REF}, {"CONSORTIUM_MODEL": phase0.MODEL_REF}))
        self.assertFalse(phase0.validate_child_env(ambient, ambient))

    def test_nested_state_identity_and_explicit_adapter_are_supported(self) -> None:
        nested = {"success": True, "data": {"model": {"provider": phase0.MODEL_PROVIDER, "id": phase0.MODEL_ID}, "thinkingLevel": "off"}}
        self.assertTrue(phase0.validate_executor_state(nested)["pass"])
        adapted = {"success": True, "data": {"selected": {"vendor": phase0.MODEL_PROVIDER, "name": phase0.MODEL_ID}, "thinking": "off"}}
        adapter = lambda data: {"provider": data["selected"]["vendor"], "model": data["selected"]["name"], "thinking": data["thinking"]}
        self.assertFalse(phase0.validate_executor_state(adapted)["pass"])
        self.assertTrue(phase0.validate_executor_state(adapted, adapter)["pass"])

    def test_missing_or_malformed_state_identity_fails(self) -> None:
        missing = {"success": True, "data": {"thinkingLevel": "off"}}
        malformed = {"success": True, "data": {"model": phase0.MODEL_REF, "thinkingLevel": "off"}}
        ambient_fallback = {"success": True, "data": {"model": {"provider": "ambient", "id": "provider"}, "thinkingLevel": "off"}}
        self.assertFalse(phase0.validate_executor_state(missing)["pass"])
        self.assertFalse(phase0.validate_executor_state(malformed)["pass"])
        self.assertFalse(phase0.validate_executor_state(ambient_fallback)["pass"])

    def test_settings_path_and_payload_are_exact(self) -> None:
        workspace = Path("/tmp/c05-workspace")
        path, payload = phase0.settings_spec(workspace, enabled=True)
        self.assertEqual(path, workspace / ".pi" / "settings.json")
        self.assertTrue(phase0.validate_settings_spec(workspace, path, payload, enabled=True))
        self.assertFalse(phase0.validate_settings_spec(workspace, workspace / "settings.json", payload, enabled=True))
        self.assertFalse(phase0.validate_settings_spec(workspace, path, {"consortium": {}}, enabled=True))

    def test_reviewer_command_shape_is_pinned_but_not_availability_claim(self) -> None:
        workspace, sessions, name = Path("/tmp/workspace"), Path("/tmp/sessions"), "review-name"
        command = phase0.build_reviewer_command(workspace, sessions, name)
        self.assertTrue(phase0.validate_reviewer_command(command, workspace, sessions, name))
        self.assertEqual(command[command.index("--provider") + 1], phase0.MODEL_PROVIDER)
        self.assertEqual(command[command.index("--model") + 1], phase0.MODEL_ID)
        self.assertFalse(phase0.validate_reviewer_command(command[:-1], workspace, sessions, name))

    def test_publication_dry_run_is_confined_to_authorized_root_without_writing(self) -> None:
        with repository_tempdir() as temp:
            root = Path(temp)
            result = phase0.publication_dry_run(root, ["alpha", "beta"])
            self.assertTrue(result["pass"])
            self.assertTrue(result["dry_run"])
            self.assertFalse((root / "alpha").exists())
            (root / "alpha").mkdir()
            self.assertFalse(phase0.publication_dry_run(root, ["alpha"])["pass"])
            with self.assertRaises(ValueError):
                phase0.publication_dry_run(Path("relative"), ["alpha"])
            with self.assertRaises(ValueError):
                phase0.publication_dry_run(root, ["../escape"])
            with self.assertRaises(ValueError):
                phase0.publication_dry_run(root, ["duplicate", "duplicate"])


if __name__ == "__main__":
    unittest.main()
