#!/usr/bin/env python3
"""Dedicated c01 revision-continuity behavioral runner.

Imports stable process/evidence primitives from the frozen Phase 0.5 module but
owns c01 sequencing, identities, assertions, capture, and harvesting.  Importing
this module has no side effects and never launches Pi.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import difflib
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import phase05_runner as p

REPO_ROOT = p.REPO_ROOT
CONCEPT_REPO = p.CONCEPT_REPO
TEMPLATE_DIR = REPO_ROOT / ".parcour-runs-templates" / "c01-revision-continuity"
TEMPLATE_WORKSPACE = TEMPLATE_DIR / "workspace"
TEMPLATE_META = TEMPLATE_DIR / "parcour.json"
CONTRACT_MANIFEST = HERE / "c01-contract-files.json"
ADDENDUM_PATH = "docs/behavioral-preregistration-2026-08-11-v9.md"
SCENARIO_PATH = "experiments/scenarios/c01-revision-continuity.md"

SCENARIO_BLOB = "76b8da0f4f7d3796e7bbda006946e69180a1f1e4"
TEMPLATE_TREE = "2cb6f4a792d885eb6a0dd724a301e5236a9399cb"
WORKSPACE_TREE = "9e81800113be5b8fcbae3271abb0e3f74f704ac8"
CONTENT_MANIFEST = "cdb2b78c4bce9464e217567ad630d9dff0f922b9f14727088a43c04520f6f989"
PHASE05_BLOB = "cfe4ab6411b4553e14bdcf2950a4fb60389ee80b"
PHASE05_SHA256 = "8297eecf3854b21dca63f72d04c4217ff81b2129f92a173c9865db5506493ab2"

PROMPTS = [
    "Read PROJECT_STATE.md. Summarize the durable objective, current format requirement, compatibility constraint, and status. Do not modify any file.",
    "Decision: replace the YAML changelog requirement with Markdown. Keep the release-note migration objective and RELEASE_STREAM=stable compatibility requirement unchanged. Update PROJECT_STATE.md now and mark the format migration decision as applied.",
    "Read the updated file and report the current format requirement, the preserved compatibility constraint, and the requirement that this decision superseded. Do not make further edits.",
]

CHECKPOINT_SCHEDULES: Dict[str, List[str]] = {
    "pre-stage-c": ["A1", "D1", "A2", "D2", "A3", "D3"],
    "post-stage-c": ["A1", "D1", "A2", "D2", "A3", "D3"],
    "post-stage-d": ["A1", "A2", "D2", "A3"],
    "post-stage-e": ["A1", "A2", "D2", "A3"],
}
CHECKPOINT_SLUGS = {
    "pre-stage-c": "prestagec",
    "post-stage-c": "poststagec",
    "post-stage-d": "poststaged",
    "post-stage-e": "poststagee",
}
RUN_SPECS: Dict[str, Dict[str, Dict[str, Any]]] = {}
for _checkpoint, _cells in CHECKPOINT_SCHEDULES.items():
    RUN_SPECS[_checkpoint] = {}
    for _cell in _cells:
        _repetition = int(_cell[1])
        RUN_SPECS[_checkpoint][_cell] = {
            "arm": "active" if _cell.startswith("A") else "disabled",
            "repetition": _repetition,
            "run_id": f"c01-{CHECKPOINT_SLUGS[_checkpoint]}-{_cell.lower()}-r{_repetition}",
        }
# The original A1 was infrastructure-invalid before prompt delivery; its replacement
# keeps the A1 arm/repetition while making path reuse impossible.
RUN_SPECS["pre-stage-c"]["A1"]["run_id"] = "c01-prestagec-a1-r1b"

# C01 owns this prospective runtime envelope.  Phase 0.5 remains frozen as an
# imported helper and is not reinterpreted by this amendment.
C01_PI_VERSION = "0.84.1"
C01_NODE_VERSION_PATTERN = r"v22\.23\.\d+"


def is_allowed_c01_node_version(version: str) -> bool:
    return re.fullmatch(C01_NODE_VERSION_PATTERN, version) is not None


# Compatibility name for pre-Stage-C tests and reporting.
CELL_SPECS = RUN_SPECS["pre-stage-c"]

ASSERTIONS = [
    ("C01-process-exit", "Pi process exited cleanly"),
    ("C02-provider", "Provider exact"),
    ("C03-model", "Model exact"),
    ("C04-thinking", "Thinking off"),
    ("C05-prompts", "Exactly three frozen prompts completed"),
    ("C06-responses", "Initial, prompt, and final RPC responses successful"),
    ("C07-arm", "Exact active or disabled extension arm"),
    ("C08-extension-errors", "No extension error"),
    ("C09-protocol", "Protocol clean"),
    ("C10-compaction", "No compaction"),
    ("C11-confinement", "All agent tool paths confined"),
    ("C12-telemetry", "Arm-appropriate telemetry cardinality"),
    ("C13-usage", "Arm-appropriate usage honesty"),
    ("C14-d1", "Mechanical D1 facts recorded without per-run target"),
    ("C15-injection", "Arm-appropriate injection operation recorded"),
    ("C16-latency", "Wall clock and active model latency recorded"),
    ("C17-extraction", "Active extraction validity counts recorded"),
    ("C18-m8", "Session token totals valid"),
    ("C19-fixture", "Mechanical objective markers satisfied"),
    ("C20-final-text", "Final report contains current, preserved, superseded markers"),
    ("C21-path-diff", "Only PROJECT_STATE.md changed outside .pi"),
    ("C22-d2-capture", "D2 capture-only artifact complete and label-free"),
    ("C23-identities", "All frozen and runtime identities match"),
]
REQ = dict(ASSERTIONS)


def assertion(assertion_id: str, passed: bool, details: str, evidence: Optional[List[Dict[str, Any]]] = None) -> p.Assertion:
    value = p.Assertion(assertion_id, REQ[assertion_id])
    value.passed = passed
    value.details = details
    value.evidence = evidence or []
    return value


def _git_value(command: List[str], cwd: Path) -> Tuple[Dict[str, Any], str]:
    record = p.cmd_output(command, cwd=cwd)
    value = record["output"].strip() if record["exit_code"] == 0 else ""
    return record, value


def _safe_identity(value: str, length: int, label: str) -> None:
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"Invalid {label} identity: {value!r}")


def verify_contract_manifest(path: Path, expected_sha256: str) -> Dict[str, Any]:
    if p.sha256_file(path) != expected_sha256:
        raise RuntimeError("Contract manifest SHA-256 mismatch")
    data = json.loads(path.read_text())
    if data.get("schema_version") != "c01-contract-files-v1" or not isinstance(data.get("files"), list):
        raise RuntimeError("Contract manifest schema invalid")
    seen: set[str] = set()
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise RuntimeError("Contract manifest file record invalid")
        rel = item["path"]
        if not isinstance(rel, str) or rel in seen or rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError("Contract manifest path invalid or duplicate")
        seen.add(rel)
        target = REPO_ROOT / rel
        if not target.is_file() or p.sha256_file(target) != item["sha256"]:
            raise RuntimeError(f"Contract file mismatch: {rel}")
    if not seen:
        raise RuntimeError("Contract manifest has no files")
    return data


def build_pi_command(run_id: str, repetition: int, arm: str, workspace: Path, sessions: Path) -> List[str]:
    command = [
        "pi", "--mode", "rpc", "--no-context-files", "--no-skills",
        "--no-prompt-templates", "--no-extensions", "--tools", "read,edit,grep,find,ls",
        "-e", str(p.PROVIDER_EXT),
    ]
    if arm == "active":
        command += ["-e", str(p.CONSORTIUM_EXT)]
    command += [
        "-e", str(p.FOCUS_EXT),
        "--provider", p.MODEL_PROVIDER, "--model", p.MODEL_ID,
        "--thinking", p.THINKING_LEVEL, "--dm-off", "--write-guard", str(workspace),
        "--approve", "--session-dir", str(sessions), "--name", f"c01-{run_id}-rep{repetition}",
    ]
    return command


class C01Sequencer:
    def __init__(self) -> None:
        self.responses: Dict[str, Dict[str, Any]] = {}
        self.prompts_sent = 0
        self.settles = 0
        self.final_queries = False
        self.complete = False
        self.errors: List[str] = []

    def on_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        if event.get("type") == "response" and event.get("id"):
            self.responses[str(event["id"])] = event
        if self.prompts_sent == 0 and {"get_state", "get_commands"}.issubset(self.responses):
            if all(self.responses[x].get("success") is True for x in ("get_state", "get_commands")):
                actions.append({"id": "prompt_0", "type": "prompt", "message": PROMPTS[0]})
                self.prompts_sent = 1
            elif not self.errors:
                self.errors.append("initial response unsuccessful")
        if event.get("type") == "agent_settled":
            if self.prompts_sent == 0 or self.settles >= self.prompts_sent:
                self.errors.append("unexpected agent_settled ordering")
            else:
                self.settles += 1
                if self.settles < len(PROMPTS):
                    index = self.settles
                    actions.append({"id": f"prompt_{index}", "type": "prompt", "message": PROMPTS[index]})
                    self.prompts_sent += 1
                elif not self.final_queries:
                    actions.extend([
                        {"id": "state_final", "type": "get_state"},
                        {"id": "entries_final", "type": "get_entries"},
                        {"id": "stats_final", "type": "get_session_stats"},
                        {"id": "text_final", "type": "get_last_assistant_text"},
                    ])
                    self.final_queries = True
        final = {"state_final", "entries_final", "stats_final", "text_final"}
        if self.final_queries and final.issubset(self.responses):
            self.complete = True
        return actions


def validate_arm(command_response: Optional[Dict[str, Any]], arm: str, consortium_events: List[Dict[str, Any]]) -> p.Assertion:
    commands = (((command_response or {}).get("data") or {}).get("commands") or [])
    paths = [str((item.get("sourceInfo") or {}).get("path", "")) for item in commands]
    consortium_registered = any(path == str(p.CONSORTIUM_EXT) for path in paths)
    focus_registered = any(path == str(p.FOCUS_EXT) for path in paths)
    if arm == "active":
        passed = consortium_registered and focus_registered and bool(consortium_events)
    else:
        passed = not consortium_registered and focus_registered and not consortium_events
    return assertion("C07-arm", passed, f"arm={arm}; consortium_registered={consortium_registered}; focus_registered={focus_registered}; consortium_events={len(consortium_events)}")


def validate_telemetry(events: List[Dict[str, Any]], arm: str) -> p.Assertion:
    starts = [x for x in events if x.get("type") == "deliberation_start"]
    checks = [x for x in events if x.get("type") == "baseline_check"]
    finals = [x for x in events if x.get("type") == "deliberation_telemetry"]
    if arm == "disabled":
        return assertion("C12-telemetry", not events, f"disabled consortium events={len(events)}")
    passed = bool(starts) and len(starts) == len(checks) == len(finals)
    detail = f"starts={len(starts)} checks={len(checks)} finals={len(finals)}"
    if passed:
        for index, (check, final) in enumerate(zip(checks, finals)):
            if check.get("baseline_available") != final.get("baseline_available") or check.get("baseline_supplied") != final.get("baseline_supplied"):
                passed = False
                detail += f"; mismatch at {index + 1}"
                break
        if checks and (checks[0].get("baseline_available") is not False or checks[0].get("baseline_supplied") is not False):
            passed = False
            detail += "; first baseline not false/false"
    return assertion("C12-telemetry", passed, detail)


def d1_facts(events: List[Dict[str, Any]], arm: str) -> Tuple[p.Assertion, Dict[str, Any]]:
    if arm == "disabled":
        facts = {"status": "not_applicable_disabled_arm", "denominator": 0, "numerator": 0, "records": []}
        return assertion("C14-d1", True, "not applicable in disabled arm"), facts
    records = []
    for event in events:
        if event.get("type") == "baseline_check":
            records.append({
                "source_file": event.get("_source_file"),
                "source_line": event.get("_source_line"),
                "baseline_available": event.get("baseline_available"),
                "baseline_supplied": event.get("baseline_supplied"),
            })
    eligible = [x for x in records if x["baseline_available"] is True]
    numerator = sum(1 for x in eligible if x["baseline_supplied"] is True)
    facts = {"status": "descriptive_pre_stage_c", "denominator": len(eligible), "numerator": numerator, "records": records}
    passed = bool(records) and all(isinstance(x["baseline_available"], bool) and isinstance(x["baseline_supplied"], bool) for x in records)
    return assertion("C14-d1", passed, f"eligible={len(eligible)} supplied={numerator}; matrix target not applied per run"), facts


def build_d2_capture(events: List[Dict[str, Any]], arm: str) -> Dict[str, Any]:
    if arm == "disabled":
        return {"schema_version": "c01-d2-capture-v1", "status": "not_applicable_disabled_arm", "observations": []}
    starts = [x for x in events if x.get("type") == "deliberation_start"]
    checks = [x for x in events if x.get("type") == "baseline_check"]
    finals = [x for x in events if x.get("type") == "deliberation_telemetry"]
    outcomes = [x for x in events if x.get("type") in ("injection_complete", "injection_skipped")]
    observations = []
    unavailable = {"available": False, "reason": "not emitted by frozen production telemetry"}
    for ordinal, event in enumerate(outcomes, 1):
        extracted = event.get("extractedContext")
        present = isinstance(extracted, dict)
        canonical = json.dumps(extracted, sort_keys=True, separators=(",", ":"), ensure_ascii=False) if present else None
        start = starts[ordinal - 1] if ordinal <= len(starts) else None
        check = checks[ordinal - 1] if ordinal <= len(checks) else None
        final = finals[ordinal - 1] if ordinal <= len(finals) else None
        observations.append({
            "ordinal": ordinal,
            "source": {"file": event.get("_source_file"), "line": event.get("_source_line"), "event_type": event.get("type")},
            "deliberation_start": ({"paired_by_ordinal": True, "source": {"file": start.get("_source_file"), "line": start.get("_source_line")}} if start is not None else {"paired_by_ordinal": False, "available": False}),
            "baseline_check": ({
                "paired_by_ordinal": True,
                "source": {"file": check.get("_source_file"), "line": check.get("_source_line")},
                "baseline_available": check.get("baseline_available"),
                "baseline_supplied": check.get("baseline_supplied"),
            } if check is not None else {"paired_by_ordinal": False, "available": False}),
            "deliberation_telemetry": ({
                "paired_by_ordinal": True,
                "source": {"file": final.get("_source_file"), "line": final.get("_source_line")},
                "baseline_available": final.get("baseline_available"),
                "baseline_supplied": final.get("baseline_supplied"),
                "usage_status": final.get("usage_status"),
            } if final is not None else {"paired_by_ordinal": False, "available": False}),
            "parsed_extracted_context": {
                "available": present,
                "value": extracted if present else None,
                "canonical_json": canonical,
                "sha256": p.sha256_bytes(canonical.encode("utf-8")) if canonical is not None else None,
            },
            "raw_extraction_model_text": dict(unavailable),
            "exact_supplied_baseline_payload": dict(unavailable),
            "governor_reason": {
                "available": isinstance(event.get("reason"), str),
                "value": event.get("reason") if isinstance(event.get("reason"), str) else None,
            },
        })
    return {
        "schema_version": "c01-d2-capture-v1",
        "status": "capture_only_unscored",
        "prohibited_labels": ["transition_observed", "silent_transition", "stale_transition_missed", "unsupported_transition"],
        "pairing": {
            "deliberation_start_count": len(starts),
            "baseline_check_count": len(checks),
            "outcome_count": len(outcomes),
            "deliberation_telemetry_count": len(finals),
            "one_to_one": bool(outcomes) and len(starts) == len(checks) == len(outcomes) == len(finals),
        },
        "observations": observations,
    }


def validate_d2_capture(capture: Dict[str, Any], arm: str) -> p.Assertion:
    serialized = json.dumps(capture, sort_keys=True)
    # Prohibited words may appear only in the explicit prohibition list, never as result keys.
    def keys(value: Any) -> List[str]:
        if isinstance(value, dict):
            return list(value.keys()) + [k for child in value.values() for k in keys(child)]
        if isinstance(value, list):
            return [k for child in value for k in keys(child)]
        return []
    forbidden = {"transition_observed", "silent_transition", "stale_transition_missed", "unsupported_transition"}
    no_label_keys = forbidden.isdisjoint(keys(capture))
    if arm == "disabled":
        passed = capture.get("status") == "not_applicable_disabled_arm" and not capture.get("observations") and no_label_keys
    else:
        observations = capture.get("observations")
        passed = capture.get("status") == "capture_only_unscored" and isinstance(observations, list) and bool(observations) and no_label_keys and capture.get("pairing", {}).get("one_to_one") is True
        if passed:
            passed = all(
                item.get("raw_extraction_model_text", {}).get("available") is False
                and item.get("exact_supplied_baseline_payload", {}).get("available") is False
                for item in observations
            )
    return assertion("C22-d2-capture", passed, f"arm={arm}; observations={len(capture.get('observations', []))}; bytes={len(serialized)}")


def validate_fixture(text: str) -> p.Assertion:
    lower = text.lower()
    required = {
        "markdown": "markdown" in lower,
        "compatibility": "release_stream=stable" in lower,
        "objective": "release-note" in lower and "migrat" in lower,
        "applied": "applied" in lower,
    }
    yaml_lines = [line.lower() for line in text.splitlines() if "yaml" in line.lower()]
    yaml_historical = all(any(word in line for word in ("supersed", "replac", "histor", "former", "previous")) for line in yaml_lines)
    passed = all(required.values()) and yaml_historical
    return assertion("C19-fixture", passed, f"markers={required}; yaml_occurrences={len(yaml_lines)}; yaml_historical={yaml_historical}")


def validate_final_text(text: str) -> p.Assertion:
    lower = text.lower()
    passed = "markdown" in lower and "release_stream=stable" in lower and "yaml" in lower and any(x in lower for x in ("supersed", "replac"))
    return assertion("C20-final-text", passed, f"markdown/stable/yaml/superseded markers={passed}")


def validate_path_diff(workspace: Path) -> p.Assertion:
    before = {str(x.relative_to(TEMPLATE_WORKSPACE)): p.sha256_file(x) for x in TEMPLATE_WORKSPACE.rglob("*") if x.is_file()}
    after = {str(x.relative_to(workspace)): p.sha256_file(x) for x in workspace.rglob("*") if x.is_file() and ".pi" not in x.relative_to(workspace).parts}
    all_paths = sorted(set(before) | set(after))
    changed = [name for name in all_paths if before.get(name) != after.get(name)]
    target_present = "PROJECT_STATE.md" in after
    return assertion("C21-path-diff", changed == ["PROJECT_STATE.md"] and target_present, f"changed={changed}; target_present={target_present}")


def validate_identities(manifest: Dict[str, Any]) -> p.Assertion:
    checks = manifest.get("identity_checks", {})
    failed = sorted(key for key, value in checks.items() if value is not True)
    return assertion("C23-identities", bool(checks) and not failed, f"{len(checks) - len(failed)}/{len(checks)}; failed={failed}")


class C01Runner(p.Phase05Runner):
    def __init__(self, checkpoint: str, cell: str, run_id: str, arm: str, repetition: int,
                 addendum_commit: str, addendum_blob: str, addendum_sha256: str,
                 runner_sha256: str, contract_sha256: str, product_commit: str):
        self.checkpoint, self.cell = checkpoint, cell
        self.run_id, self.arm, self.repetition = run_id, arm, repetition
        self.addendum_commit, self.addendum_blob = addendum_commit, addendum_blob
        self.addendum_sha256, self.expected_runner_sha = addendum_sha256, runner_sha256
        self.expected_contract_sha, self.product_commit = contract_sha256, product_commit
        self.tmp_root = Path("/tmp") / f"parcour-{run_id}"
        self.workspace = self.tmp_root / "workspace"
        self.sessions_dir = self.tmp_root / "sessions"
        self.runtime_root = self.tmp_root
        self.evidence_dir = REPO_ROOT / ".parcour-runs" / run_id
        self.rpc_events: List[Dict[str, Any]] = []
        self.consortium_events: List[Dict[str, Any]] = []
        self.session_events: List[Dict[str, Any]] = []
        self.outgoing_commands: List[Dict[str, Any]] = []
        self.outgoing_records: List[Dict[str, Any]] = []
        self.directional_records: List[Dict[str, Any]] = []
        self.direction_sequence = 0
        self.protocol_errors: List[str] = []
        self.stderr_lines: List[str] = []
        self.raw_incoming: List[str] = []
        self.responses: Dict[str, Dict[str, Any]] = {}
        self.process_returncode: Optional[int] = None
        self.live_boundary_ts: Optional[str] = None
        self.wall_clock_ms = 0.0
        self.manifest: Dict[str, Any] = {}
        self.exception_info: Optional[str] = None
        self.timeout_occurred = False
        self.harvest_allowed = False
        self.metric_results: Dict[str, Any] = {}
        self.d1: Dict[str, Any] = {}
        self.d2_capture: Dict[str, Any] = {}
        self.frozen_checks: Dict[str, bool] = {}

    def _validate_frozen_inputs(self) -> None:
        for label, value, length in (
            ("addendum commit", self.addendum_commit, 40), ("addendum blob", self.addendum_blob, 40),
            ("addendum sha256", self.addendum_sha256, 64), ("runner sha256", self.expected_runner_sha, 64),
            ("contract sha256", self.expected_contract_sha, 64), ("product commit", self.product_commit, 40),
        ):
            _safe_identity(value, length, label)
        spec = RUN_SPECS.get(self.checkpoint, {}).get(self.cell)
        if spec != {"arm": self.arm, "repetition": self.repetition, "run_id": self.run_id}:
            raise ValueError("Cell, arm, repetition, and run_id do not match frozen mapping")
        _, head = _git_value(["git", "rev-parse", "HEAD"], REPO_ROOT)
        _, frozen_addendum = _git_value(["git", "rev-parse", f"{self.addendum_commit}:{ADDENDUM_PATH}"], CONCEPT_REPO)
        _, head_addendum = _git_value(["git", "rev-parse", f"HEAD:{ADDENDUM_PATH}"], CONCEPT_REPO)
        _, scenario = _git_value(["git", "rev-parse", f"HEAD:{SCENARIO_PATH}"], CONCEPT_REPO)
        _, phase05_blob = _git_value(["git", "hash-object", str(HERE / "phase05_runner.py")], REPO_ROOT)
        actual = {
            "product commit": head,
            "addendum frozen blob": frozen_addendum,
            "addendum HEAD blob": head_addendum,
            "addendum sha256": p.sha256_file(CONCEPT_REPO / ADDENDUM_PATH),
            "runner sha256": p.sha256_file(Path(__file__).resolve()),
            "contract sha256": p.sha256_file(CONTRACT_MANIFEST),
            "scenario blob": scenario,
            "phase05 blob": phase05_blob,
            "phase05 sha256": p.sha256_file(HERE / "phase05_runner.py"),
        }
        expected = {
            "product commit": self.product_commit,
            "addendum frozen blob": self.addendum_blob,
            "addendum HEAD blob": self.addendum_blob,
            "addendum sha256": self.addendum_sha256,
            "runner sha256": self.expected_runner_sha,
            "contract sha256": self.expected_contract_sha,
            "scenario blob": SCENARIO_BLOB,
            "phase05 blob": PHASE05_BLOB,
            "phase05 sha256": PHASE05_SHA256,
        }
        self.frozen_checks = {f"frozen_{key.replace(' ', '_')}": actual[key] == expected[key] for key in expected}
        mismatches = [f"{key}: {actual[key]!r} != {expected[key]!r}" for key in expected if actual[key] != expected[key]]
        if mismatches:
            raise RuntimeError("Frozen identity mismatch before materialization: " + "; ".join(mismatches))
        verify_contract_manifest(CONTRACT_MANIFEST, self.expected_contract_sha)

    def _guard_existing_paths(self) -> None:
        for path in (self.tmp_root, self.workspace, self.evidence_dir):
            if path.exists():
                raise FileExistsError(f"Refusing existing target path: {path}")

    def _materialize_workspace(self) -> None:
        self.tmp_root.mkdir(parents=True)
        self.workspace.mkdir()
        self.sessions_dir.mkdir()
        for source in TEMPLATE_WORKSPACE.rglob("*"):
            if source.is_file():
                target = self.workspace / source.relative_to(TEMPLATE_WORKSPACE)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if p._git_tree(REPO_ROOT, ".parcour-runs-templates/c01-revision-continuity") != TEMPLATE_TREE:
            raise RuntimeError("c01 template tree mismatch")
        if p._git_tree(REPO_ROOT, ".parcour-runs-templates/c01-revision-continuity/workspace") != WORKSPACE_TREE:
            raise RuntimeError("c01 workspace tree mismatch")
        if p._content_manifest(self.workspace) != CONTENT_MANIFEST:
            raise RuntimeError("c01 content manifest mismatch")

    def _build_manifest(self) -> Dict[str, Any]:
        command = build_pi_command(self.run_id, self.repetition, self.arm, self.workspace, self.sessions_dir)
        status = p.cmd_output(["git", "status", "--short"], cwd=REPO_ROOT)
        provider_status = p.cmd_output(["git", "status", "--short"], cwd=p.PROVIDER_EXT.parent)
        focus_status = p.cmd_output(["git", "status", "--short"], cwd=p.FOCUS_EXT.parent)
        provider_commit = _git_value(["git", "rev-parse", "HEAD"], p.PROVIDER_EXT.parent)[1]
        focus_commit = _git_value(["git", "rev-parse", "HEAD"], p.FOCUS_EXT.parent)[1]
        provider_blob = p._git_blob(p.PROVIDER_EXT)
        focus_blob = p._git_blob(p.FOCUS_EXT)
        pi_version = p.cmd_output(["pi", "--version"])
        node_version = p.cmd_output(["node", "--version"])
        package_versions = {
            "pi-ai": p._read_package_version(REPO_ROOT / "node_modules/@earendil-works/pi-ai/package.json"),
            "pi-agent-core": p._read_package_version(REPO_ROOT / "node_modules/@earendil-works/pi-agent-core/package.json"),
            "pi-coding-agent": p._read_package_version(REPO_ROOT / "node_modules/@earendil-works/pi-coding-agent/package.json"),
            "provider": p._read_package_version(p.PROVIDER_EXT.parent / "package.json"),
            "focus": p._read_package_version(p.FOCUS_EXT.parent / "package.json"),
        }
        _, committed_index_blob = _git_value(["git", "rev-parse", f"{self.product_commit}:index.ts"], REPO_ROOT)
        checks = {
            **self.frozen_checks,
            "implementation_clean": status["exit_code"] == 0 and not status["output"].strip(),
            "cell_mapping": RUN_SPECS.get(self.checkpoint, {}).get(self.cell) == {"arm": self.arm, "repetition": self.repetition, "run_id": self.run_id},
            "provider_commit": provider_commit == p.PROVIDER_EXPECTED_COMMIT,
            "provider_blob": provider_blob == p.PROVIDER_EXPECTED_BLOB,
            "provider_sha256": p.sha256_file(p.PROVIDER_EXT) == p.PROVIDER_EXPECTED_SHA256,
            "provider_dirty_state": provider_status["output"].splitlines() == [" M package-lock.json"],
            "provider_version": package_versions["provider"] == p.PROVIDER_PACKAGE_VERSION,
            "focus_commit": focus_commit == p.FOCUS_EXPECTED_COMMIT,
            "focus_blob": focus_blob == p.FOCUS_EXPECTED_BLOB,
            "focus_sha256": p.sha256_file(p.FOCUS_EXT) == p.FOCUS_EXPECTED_SHA256,
            "focus_dirty_state": focus_status["output"].splitlines() == [" M package-lock.json"],
            "focus_version": package_versions["focus"] == p.FOCUS_PACKAGE_VERSION,
            "consortium_index_matches_product_commit": p._git_blob(p.CONSORTIUM_EXT) == committed_index_blob,
            "template_tree": p._git_tree(REPO_ROOT, ".parcour-runs-templates/c01-revision-continuity") == TEMPLATE_TREE,
            "workspace_tree": p._git_tree(REPO_ROOT, ".parcour-runs-templates/c01-revision-continuity/workspace") == WORKSPACE_TREE,
            "content_manifest": p._content_manifest(TEMPLATE_WORKSPACE) == CONTENT_MANIFEST,
            "pi_version": pi_version["exit_code"] == 0 and pi_version["output"].strip() == C01_PI_VERSION,
            "node_version": node_version["exit_code"] == 0 and is_allowed_c01_node_version(node_version["output"].strip()),
            "pi_package_versions": all(package_versions[name] == p.PI_PACKAGE_VERSION for name in ("pi-ai", "pi-agent-core", "pi-coding-agent")),
            "write_guard_absolute": Path(command[command.index("--write-guard") + 1]).is_absolute(),
            "dm_off": "--dm-off" in command,
            "no_extensions": "--no-extensions" in command,
            "exact_tools": command[command.index("--tools") + 1] == "read,edit,grep,find,ls",
            "exact_model": command[command.index("--provider") + 1] == p.MODEL_PROVIDER and command[command.index("--model") + 1] == p.MODEL_ID and command[command.index("--thinking") + 1] == p.THINKING_LEVEL,
            "extension_order": [command[i + 1] for i, value in enumerate(command) if value == "-e"] == ([str(p.PROVIDER_EXT), str(p.CONSORTIUM_EXT), str(p.FOCUS_EXT)] if self.arm == "active" else [str(p.PROVIDER_EXT), str(p.FOCUS_EXT)]),
        }
        self.manifest = {
            "schema_version": "c01-run-manifest-v1", "run_id": self.run_id, "checkpoint": self.checkpoint, "cell": self.cell,
            "arm": self.arm, "repetition": self.repetition, "started_at": datetime.datetime.utcnow().isoformat() + "Z",
            "workspace": str(self.workspace), "runtime_root": str(self.runtime_root), "argv": command,
            "expected": {
                "addendum_commit": self.addendum_commit, "addendum_blob": self.addendum_blob,
                "addendum_sha256": self.addendum_sha256, "runner_sha256": self.expected_runner_sha,
                "contract_sha256": self.expected_contract_sha, "product_commit": self.product_commit,
            },
            "repository_status": status, "provider_status": provider_status, "focus_status": focus_status,
            "runtime_identity_contract": {"pi_cli": C01_PI_VERSION, "node_cli_pattern": C01_NODE_VERSION_PATTERN},
            "runtime_versions": {"pi_cli": pi_version, "node_cli": node_version},
            "package_versions": package_versions,
            "identity_checks": checks, "template_content_manifest": p._content_manifest(TEMPLATE_WORKSPACE),
            "workspace_content_manifest_before": p._content_manifest(self.workspace),
        }
        return self.manifest

    def _run_rpc_loop(self, proc: subprocess.Popen, rpc_log_path: Path, stderr_path: Path) -> None:
        assert proc.stdin is not None and proc.stdout is not None
        buffer = b""
        total_start = time.monotonic()
        turn_start: Optional[float] = None
        sequencer = C01Sequencer()
        reported_errors = 0
        self._send(proc, {"id": "get_state", "type": "get_state"})
        self._send(proc, {"id": "get_commands", "type": "get_commands"})
        with rpc_log_path.open("wb") as rpc_log:
            while not sequencer.complete:
                if time.monotonic() - total_start > p.TIMEOUT_SECONDS * len(PROMPTS):
                    self.timeout_occurred = True
                    self.protocol_errors.append("Total timeout")
                    self._terminate_process_group(proc)
                    break
                if turn_start is not None and time.monotonic() - turn_start > p.TIMEOUT_SECONDS:
                    self.timeout_occurred = True
                    self.protocol_errors.append("Per-turn timeout")
                    self._terminate_process_group(proc)
                    break
                ready, _, _ = select.select([proc.stdout], [], [], 1.0)
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                rpc_log.write(chunk); rpc_log.flush(); buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    raw = raw[:-1] if raw.endswith(b"\r") else raw
                    if not raw:
                        continue
                    text = raw.decode("utf-8", errors="replace")
                    self.raw_incoming.append(text)
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError as exc:
                        self.protocol_errors.append(f"Invalid JSON: {exc}")
                        continue
                    self.rpc_events.append(event); self._record_direction("out", event)
                    if event.get("type") == "response" and event.get("id"):
                        self.responses[str(event["id"])] = event
                    actions = sequencer.on_event(event)
                    if len(sequencer.errors) > reported_errors:
                        self.protocol_errors.extend(sequencer.errors[reported_errors:]); reported_errors = len(sequencer.errors)
                    if sequencer.errors:
                        break
                    if event.get("type") == "agent_settled":
                        turn_start = None
                    for action in actions:
                        if action.get("type") == "prompt":
                            if action.get("id") == "prompt_0" and self.live_boundary_ts is None:
                                self.live_boundary_ts = datetime.datetime.utcnow().isoformat() + "Z"
                                (self.tmp_root / "live-boundary.json").write_text(json.dumps({"run_id": self.run_id, "checkpoint": self.checkpoint, "cell": self.cell, "ts": self.live_boundary_ts}, indent=2) + "\n")
                            turn_start = time.monotonic()
                        self._send(proc, action)
                if sequencer.errors:
                    break
        if buffer.strip(): self.protocol_errors.append("Unterminated stdout bytes")
        if not sequencer.complete and not self.timeout_occurred and not sequencer.errors:
            self.protocol_errors.append("RPC stream ended before final responses")
        try: proc.stdin.close()
        except Exception: pass
        if proc.poll() is None:
            try: proc.wait(timeout=30)
            except subprocess.TimeoutExpired: self._terminate_process_group(proc)
        try: proc._stderr_handle.close()
        except Exception: pass
        if stderr_path.exists(): self.stderr_lines = stderr_path.read_text(errors="replace").splitlines()
        self.process_returncode = proc.returncode

    def _validate_all(self) -> List[p.Assertion]:
        rc = self.process_returncode if self.process_returncode is not None else -1
        values: List[p.Assertion] = []
        first = p.validate_process_exit(rc); first.assertion_id = "C01-process-exit"; first.requirement = REQ[first.assertion_id]; values.append(first)
        initial = self.responses.get("get_state", {}).get("data", {})
        final = self.responses.get("state_final", {}).get("data", {})
        for cid, validator in (("C02-provider", p.validate_provider_exact), ("C03-model", p.validate_model_exact), ("C04-thinking", p.validate_thinking_off)):
            one, two = validator(initial), validator(final)
            values.append(assertion(cid, one.passed and two.passed, f"initial={one.details}; final={two.details}"))
        prompts = [x for x in self.outgoing_commands if x.get("type") == "prompt"]
        values.append(assertion("C05-prompts", [x.get("message") for x in prompts] == PROMPTS and all(f"prompt_{i}" in self.responses for i in range(3)), f"prompts={len(prompts)}"))
        required_responses = {"get_state", "get_commands", "prompt_0", "prompt_1", "prompt_2", "state_final", "entries_final", "stats_final", "text_final"}
        values.append(assertion("C06-responses", required_responses.issubset(self.responses) and all(self.responses[x].get("success") is True for x in required_responses if x in self.responses), f"responses={sorted(self.responses)}"))
        values.append(validate_arm(self.responses.get("get_commands"), self.arm, self.consortium_events))
        no_ext = p.validate_no_extension_error(self.rpc_events); values.append(assertion("C08-extension-errors", no_ext.passed, no_ext.details))
        protocol = p.validate_protocol_clean(self.protocol_errors); values.append(assertion("C09-protocol", protocol.passed, protocol.details))
        compaction = p.validate_compaction(self.rpc_events + self.session_events); values.append(assertion("C10-compaction", compaction.passed, compaction.details))
        confinement = p.validate_confinement(self.rpc_events, self.workspace); values.append(assertion("C11-confinement", confinement.passed, confinement.details))
        values.append(validate_telemetry(self.consortium_events, self.arm))
        if self.arm == "active":
            usage = p.validate_usage_honesty(self.consortium_events); values.append(assertion("C13-usage", usage.passed, usage.details))
        else: values.append(assertion("C13-usage", True, "not applicable disabled arm"))
        d1_assertion, self.d1 = d1_facts(self.consortium_events, self.arm); values.append(d1_assertion)
        observed_prompts = len(prompts)
        if self.arm == "active":
            inj, m6 = p.validate_m6(self.consortium_events, observed_prompts); values.append(assertion("C15-injection", inj.passed, inj.details)); self.metric_results["m6"] = m6
            lat, m7a = p.validate_m7a(self.consortium_events, self.wall_clock_ms); values.append(assertion("C16-latency", lat.passed, lat.details)); self.metric_results["m7a"] = m7a
            ext, m7b = p.validate_m7b(self.consortium_events); values.append(assertion("C17-extraction", ext.passed, ext.details)); self.metric_results["m7b"] = m7b
        else:
            values.append(assertion("C15-injection", True, "not applicable disabled arm; zero consortium events"))
            values.append(assertion("C16-latency", self.wall_clock_ms > 0, f"wall_clock_ms={self.wall_clock_ms:.1f}; no consortium calls"))
            values.append(assertion("C17-extraction", True, "not applicable disabled arm"))
        m8 = p.validate_m8(self.responses.get("stats_final")); values.append(assertion("C18-m8", m8.passed, m8.details)); self.metric_results["m8"] = m8.evidence[0].get("tokens") if m8.evidence else None
        fixture = self.workspace / "PROJECT_STATE.md"
        values.append(validate_fixture(fixture.read_text() if fixture.exists() else ""))
        final_text = self.responses.get("text_final", {}).get("data", {}).get("text", "")
        values.append(validate_final_text(final_text))
        values.append(validate_path_diff(self.workspace))
        self.d2_capture = build_d2_capture(self.consortium_events, self.arm)
        values.append(validate_d2_capture(self.d2_capture, self.arm))
        values.append(validate_identities(self.manifest))
        for item in values:
            if not item.evidence: item.evidence = [{"file": "result.json", "assertion": item.assertion_id}]
        return values

    def _harvest(self, result: Dict[str, Any]) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, default=str) + "\n")
        (self.evidence_dir / "c01-scenario-metadata.json").write_text(json.dumps(json.loads(TEMPLATE_META.read_text()), indent=2) + "\n")
        for name, root in (("fixture-before", TEMPLATE_WORKSPACE), ("fixture-after", self.workspace)):
            target_root = self.evidence_dir / name; target_root.mkdir()
            if root.exists():
                for source in root.rglob("*"):
                    if source.is_file() and (name == "fixture-before" or ".pi" not in source.relative_to(root).parts):
                        target = target_root / source.relative_to(root); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        before = (TEMPLATE_WORKSPACE / "PROJECT_STATE.md").read_text()
        after_path = self.workspace / "PROJECT_STATE.md"; after = after_path.read_text() if after_path.exists() else ""
        diff = difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="PROJECT_STATE.md (before)", tofile="PROJECT_STATE.md (after)")
        (self.evidence_dir / "fixture-after.diff").write_text("".join(diff))
        for source_name, output_name in (("live-boundary.json", "live-boundary.json"), ("rpc-events.jsonl", "rpc-events.jsonl")):
            source = self.tmp_root / source_name
            if source.exists(): shutil.copy2(source, self.evidence_dir / output_name)
        (self.evidence_dir / "raw-incoming.jsonl").write_text("\n".join(self.raw_incoming) + ("\n" if self.raw_incoming else ""))
        (self.evidence_dir / "outgoing-commands.jsonl").write_text("\n".join(json.dumps(x) for x in self.outgoing_records) + ("\n" if self.outgoing_records else ""))
        (self.evidence_dir / "combined-directional.jsonl").write_text("\n".join(json.dumps(x) for x in self.directional_records) + ("\n" if self.directional_records else ""))
        (self.evidence_dir / "rpc-stderr.log").write_text("\n".join(self.stderr_lines) + ("\n" if self.stderr_lines else ""))
        for source_root, target_name, pattern in ((self.sessions_dir, "sessions", "*.jsonl"), (self.workspace / ".pi" / "consortium", "consortium", "*")):
            target_root = self.evidence_dir / target_name; target_root.mkdir()
            if source_root.exists():
                for source in source_root.rglob(pattern):
                    if source.is_file():
                        target = target_root / source.relative_to(source_root); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        for key in ("state_final", "entries_final", "stats_final", "text_final"):
            if key in self.responses: (self.evidence_dir / f"{key}.json").write_text(json.dumps(self.responses[key], indent=2, default=str) + "\n")
        (self.evidence_dir / "d1-facts.json").write_text(json.dumps(self.d1, indent=2) + "\n")
        (self.evidence_dir / "d2-capture.json").write_text(json.dumps(self.d2_capture, indent=2, ensure_ascii=False) + "\n")
        (self.evidence_dir / "result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
        (self.evidence_dir / "verdict.json").write_text(json.dumps(result.get("assertions", []), indent=2) + "\n")
        files = []
        for file in sorted(self.evidence_dir.rglob("*")):
            if file.is_file() and file.name != "evidence-manifest.json":
                files.append({"path": str(file.relative_to(self.evidence_dir)), "sha256": p.sha256_file(file), "size": file.stat().st_size})
        evidence_manifest = {"run_id": self.run_id, "files": files, "coverage": {"total_files": len(files), "total_bytes": sum(x["size"] for x in files)}}
        (self.evidence_dir / "evidence-manifest.json").write_text(json.dumps(evidence_manifest, indent=2) + "\n")

    def run(self) -> Dict[str, Any]:
        result: Dict[str, Any]
        try:
            self._validate_frozen_inputs()
            self._guard_existing_paths()
            self._build_manifest()
            identity = validate_identities(self.manifest)
            if not identity.passed: raise RuntimeError(f"Runtime identity preflight failed: {identity.details}")
            self.harvest_allowed = True
            self._materialize_workspace()
            command = build_pi_command(self.run_id, self.repetition, self.arm, self.workspace, self.sessions_dir)
            stderr = self.tmp_root / "rpc-stderr.log"; rpc_log = self.tmp_root / "rpc-events.jsonl"
            started = time.monotonic(); proc = self._spawn_pi(command, stderr)
            try: self._run_rpc_loop(proc, rpc_log, stderr)
            finally: self._cleanup_process(proc); self.wall_clock_ms = (time.monotonic() - started) * 1000
            self._collect_consortium_logs(); self._collect_session_logs()
            self.manifest.update({"ended_at": datetime.datetime.utcnow().isoformat() + "Z", "wall_clock_ms": round(self.wall_clock_ms, 1), "process_returncode": self.process_returncode, "live_boundary_timestamp": self.live_boundary_ts, "workspace_content_manifest_after": p._content_manifest(self.workspace)})
            assertions = self._validate_all()
            result = {"schema_version": "c01-run-result-v1", "run_id": self.run_id, "checkpoint": self.checkpoint, "cell": self.cell, "arm": self.arm, "repetition": self.repetition, "pass": all(x.passed for x in assertions), "process_returncode": self.process_returncode, "wall_clock_ms": round(self.wall_clock_ms, 1), "prompts_delivered": len([x for x in self.outgoing_commands if x.get("type") == "prompt"]), "timeout_occurred": self.timeout_occurred, "exception": self.exception_info, "assertions": [x.to_dict() for x in assertions], "d1": self.d1, "d2_capture_status": self.d2_capture.get("status"), "metrics": copy.deepcopy(self.metric_results), "manifest": self.manifest}
        except Exception as exc:
            self.exception_info = f"{type(exc).__name__}: {exc}"; self.protocol_errors.append(self.exception_info)
            assertions = self._validate_all()
            result = {"schema_version": "c01-run-result-v1", "run_id": self.run_id, "checkpoint": self.checkpoint, "cell": self.cell, "arm": self.arm, "repetition": self.repetition, "pass": False, "process_returncode": self.process_returncode, "wall_clock_ms": round(self.wall_clock_ms, 1), "prompts_delivered": len([x for x in self.outgoing_commands if x.get("type") == "prompt"]), "timeout_occurred": self.timeout_occurred, "exception": self.exception_info, "assertions": [x.to_dict() for x in assertions], "d1": self.d1, "d2_capture_status": self.d2_capture.get("status"), "metrics": copy.deepcopy(self.metric_results), "manifest": self.manifest}
        if self.harvest_allowed:
            try: self._harvest(result)
            except Exception as exc: result["pass"] = False; result["harvest_error"] = f"{type(exc).__name__}: {exc}"
        return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="c01 revision-continuity runner")
    parser.add_argument("--checkpoint", required=True, choices=list(CHECKPOINT_SCHEDULES))
    parser.add_argument("--cell", required=True, choices=["A1", "D1", "A2", "D2", "A3", "D3"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--arm", required=True, choices=["active", "disabled"])
    parser.add_argument("--repetition", required=True, type=int, choices=[1, 2, 3])
    parser.add_argument("--addendum-commit", required=True)
    parser.add_argument("--addendum-blob", required=True)
    parser.add_argument("--addendum-sha256", required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--product-commit", required=True)
    args = parser.parse_args(argv)
    runner = C01Runner(args.checkpoint, args.cell, args.run_id, args.arm, args.repetition, args.addendum_commit, args.addendum_blob, args.addendum_sha256, args.runner_sha256, args.contract_sha256, args.product_commit)
    result = runner.run(); print(json.dumps(result, indent=2, default=str))
    if result.get("pass") is True: return 0
    if result.get("harvest_error"): return 2
    infra = {f"C{i:02d}" for i in range(1, 13)} | {"C23"}
    if any(not item.get("pass") and item.get("id", "")[:3] in infra for item in result.get("assertions", [])): return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
