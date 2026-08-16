#!/usr/bin/env python3
"""Mechanical c05 freeze verifier; imports definitions but never launches Pi."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import c05_runner as runner
import c05_aggregate as aggregate
import c05_controller as controller

CONTRACT = HERE / "c05-contract-files.json"
LEDGER = REPO_ROOT / "docs/c05-evidence/raw-publication-ledger.json"
RAW_ROOT = REPO_ROOT / "docs/c05-raw"
C04_CORPUS = HERE / "c04-supersession-corpus.json"
C05_CORPUS = HERE / "c05-supersession-corpus.json"
PHASE0_RESULT = REPO_ROOT / "docs/c05-evidence/phase0-capability-b/result.json"
PHASE0_AUDIT = REPO_ROOT / "docs/c05-evidence/phase0-capability-b/independent-audit.md"
PATCH_COMPAT_ROOT = REPO_ROOT / "docs/c05-evidence/c05-patch-compatibility-schema-0842"
EXCLUDED_PREFIXES = ("docs/c05-raw/",)
EXCLUDED_PATHS = {str(CONTRACT.relative_to(REPO_ROOT)), str(LEDGER.relative_to(REPO_ROOT))}
EXCLUDED_EVIDENCE_PREFIXES = ("docs/c05-evidence/independent-review", "docs/c05-evidence/raw-publication", "docs/c05-evidence/c05-aggregate")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def verify_contract(freeze_commit: str | None) -> dict[str, Any]:
    data = json.loads(CONTRACT.read_text())
    if set(data) != {"schema_version", "files"} or data["schema_version"] != "c05-contract-files-v1" or not isinstance(data["files"], list) or not data["files"]:
        fail("invalid c05 contract schema")
    paths: set[str] = set()
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            fail("invalid c05 contract entry")
        rel, digest = item["path"], item["sha256"]
        if not isinstance(rel, str) or not isinstance(digest, str) or rel in paths or Path(rel).is_absolute() or ".." in Path(rel).parts:
            fail("unsafe or duplicate contract path")
        if rel in EXCLUDED_PATHS or rel.startswith(EXCLUDED_PREFIXES) or rel.startswith(EXCLUDED_EVIDENCE_PREFIXES):
            fail(f"mutable/self file in contract: {rel}")
        target = REPO_ROOT / rel
        if not target.is_file() or len(digest) != 64 or sha256(target) != digest:
            fail(f"current contract hash mismatch: {rel}")
        if freeze_commit:
            frozen = subprocess.run(["git", "show", f"{freeze_commit}:{rel}"], cwd=REPO_ROOT, capture_output=True)
            if frozen.returncode or hashlib.sha256(frozen.stdout).hexdigest() != digest:
                fail(f"freeze-commit contract hash mismatch: {rel}")
        paths.add(rel)
    required = {"scripts/behavioral-parcour/c05_runner.py", "scripts/behavioral-parcour/c05_scorer.py", "scripts/behavioral-parcour/c05-supersession-corpus.json", "scripts/behavioral-parcour/c05_controller.py", "scripts/behavioral-parcour/test_c05_controller.py", "scripts/behavioral-parcour/c05_aggregate.py", "scripts/behavioral-parcour/test_c05_aggregate.py", "docs/c05-supersession-preregistration.md", "docs/c05-supersession-preregistration.d2", "docs/c05-supersession-preregistration.svg", str(PHASE0_RESULT.relative_to(REPO_ROOT)), str(PHASE0_AUDIT.relative_to(REPO_ROOT)), "docs/c05-evidence/preflight-attempt-1-pi-version-mismatch.json", "docs/c05-evidence/preflight-attempt-1-pi-version-mismatch-diagnostic.json", *(str(path.relative_to(REPO_ROOT)) for path in PATCH_COMPAT_ROOT.iterdir() if path.is_file())}
    if not required <= paths:
        fail(f"contract missing required files: {sorted(required - paths)}")
    return {"entries": len(paths), "paths": sorted(paths)}


def verify_ledger_and_raw() -> dict[str, Any]:
    ledger = json.loads(LEDGER.read_text())
    expected = [spec["run_id"] for spec in runner.SMOKE_SPECS + runner.RUN_SPECS]
    records = ledger.get("runs")
    if set(ledger) != {"schema_version", "runs"} or ledger.get("schema_version") != "c05-raw-publication-ledger-v1" or not isinstance(records, list) or [r.get("run_id") for r in records] != expected:
        fail("ledger schema or imported schedule mismatch")
    if any(set(record) != {"run_id", "raw_directory", "status"} or record["raw_directory"] != f"docs/c05-raw/{run_id}" or record["status"] != "unconsumed" for record, run_id in zip(records, expected)):
        fail("ledger must contain only unconsumed initial records")
    found = {path.name for path in RAW_ROOT.iterdir() if path.is_dir()} if RAW_ROOT.is_dir() else set()
    if found != set(expected):
        fail("raw directory IDs mismatch")
    for run_id in expected:
        children = list((RAW_ROOT / run_id).iterdir())
        if len(children) != 1 or children[0].name != ".gitkeep" or children[0].read_bytes() != b"":
            fail(f"raw placeholder is not empty and exclusive: {run_id}")
        runtime = runner.RUN_ROOT / run_id
        if runtime.exists():
            fail(f"scheduled runtime target already exists: {run_id}")
    return {"runs": len(expected), "smoke": len(runner.SMOKE_SPECS), "matrix": len(runner.RUN_SPECS), "scheduled_runtime_targets_absent": True}


def verify_corpus_and_predicate() -> dict[str, Any]:
    c04, c05 = json.loads(C04_CORPUS.read_text()), json.loads(C05_CORPUS.read_text())
    old, new = c04["fixtures"], c05["fixtures"]
    if len(old) != len(new) != 8:
        fail("corpus fixture count mismatch")
    for before, after in zip(old, new):
        normalized = dict(after)
        if after.get("id") == "requirement-replacement":
            if normalized.pop("separator_equivalent_policy_identities", None) != ["markdown release-notes requirement", "yaml release-notes requirement"]:
                fail("authorized separator metadata missing or changed")
        if before != normalized:
            fail(f"unauthorized c04/c05 corpus delta: {before.get('id')}")
    controls = [f for f in c05["fixtures"] if f["kind"] == "control"]
    if len(controls) != 4 or any(any(key.startswith("control_") for key in fixture) for fixture in controls):
        fail("control metadata is not permitted")
    for fixture in controls:
        if runner.control_regression(fixture["before"], fixture["before"]):
            fail(f"control predicate does not preserve before text: {fixture['id']}")
    return {"fixtures": 8, "authorized_metadata_delta": "requirement-replacement.separator_equivalent_policy_identities", "controls": 4}


def verify_preregistration_and_helpers() -> dict[str, Any]:
    preregistration = (REPO_ROOT / "docs/c05-supersession-preregistration.md").read_text()
    required_markers = ("immutable valid-negative baseline", "Any failed smoke transition categorically blocks every matrix cell", "all 12 ON-positive cells fire", "all 12 OFF-positive cells do not fire", "all 24 controls do not fire", "controller has one-cell authority", "Live compatibility: Pi `0.84.*`; Node `22.*`")
    if any(marker not in preregistration for marker in required_markers):
        fail("preregistration compatibility/smoke-block/matrix mechanism/control predicate markers missing")
    accepted = {"node": "v22.23.2", "pi": "0.84.1"}
    if not runner.runtime_version_family_compatible(accepted, {"node": "v22.99.0", "pi": "0.84.2"}) or runner.runtime_version_family_compatible(accepted, {"node": "v23.0.0", "pi": "0.84.2"}) or runner.runtime_version_family_compatible(accepted, {"node": "v22.99.0", "pi": "0.85.0"}):
        fail("runtime patch-family policy implementation mismatch")
    controller_source = Path(controller.__file__).read_text()
    aggregate_source = Path(aggregate.__file__).read_text()
    if "--execute-next" not in controller_source or "if args.execute_next else 0" not in controller_source:
        fail("controller is not default read-only")
    required_aggregate_markers = ("runner.smoke_transition(smoke)", "on_fires == 12", "off_fires == 0", "control_fires == 0", '"paired_records"', '"denominators"')
    if any(marker not in aggregate_source for marker in required_aggregate_markers):
        fail("aggregate smoke/mechanism/control threshold implementation missing")
    return {"preregistration_markers": len(required_markers), "controller_default_read_only": True, "runtime_version_policy": {"pi": "0.84.*", "node": "22.*", "exact_strings_recorded": True}, "aggregate_thresholds": {"on_positive_fires": "12/12", "off_positive_fires": "0/12", "control_fires": "0/24", "on_controls_reported": "0/12"}}


def verify_phase0() -> dict[str, Any]:
    if sha256(PHASE0_RESULT) != runner.PHASE0_SHA256:
        fail("accepted Phase 0-B result SHA mismatch")
    if not PHASE0_AUDIT.is_file() or runner.validate_phase0(PHASE0_RESULT, runner.PHASE0_SHA256).get("pass") is not True:
        fail("accepted Phase 0-B evidence invalid")
    return {"result_sha256": runner.PHASE0_SHA256}


def verify_patch_compatibility_evidence() -> dict[str, Any]:
    manifest_path = PATCH_COMPAT_ROOT / "manifest.json"
    result_path = PATCH_COMPAT_ROOT / "result.json"
    manifest = json.loads(manifest_path.read_text())
    expected_names = {"audit.md", "console.json", "probe-wrapper.py", "result.json"}
    records = manifest.get("files")
    if manifest.get("schema_version") != "c05-patch-compatibility-evidence-v1" or manifest.get("run_id") != PATCH_COMPAT_ROOT.name or not isinstance(records, list) or {item.get("path") for item in records} != expected_names:
        fail("patch compatibility manifest schema/coverage mismatch")
    if any(not isinstance(item, dict) or set(item) != {"path", "sha256", "size"} or not (PATCH_COMPAT_ROOT / item["path"]).is_file() or sha256(PATCH_COMPAT_ROOT / item["path"]) != item["sha256"] or (PATCH_COMPAT_ROOT / item["path"]).stat().st_size != item["size"] for item in records):
        fail("patch compatibility evidence hash/size mismatch")
    if manifest.get("coverage") != {"files": len(records), "bytes": sum(item["size"] for item in records)}:
        fail("patch compatibility evidence coverage mismatch")
    result = json.loads(result_path.read_text())
    plan, identities, checks = result.get("plan", {}), result.get("identity", {}), result.get("checks", {})
    rpc_methods = [item.get("type") for item in plan.get("rpc_commands", []) if isinstance(item, Mapping)]
    expected_identity = {"provider": runner.MODEL_PROVIDER, "model": runner.MODEL_ID, "thinking": runner.THINKING}
    observed_versions = result.get("version_check", {}).get("observed", {})
    identity_ok = set(identities) == {"state_initial", "state_final"} and all(item.get("pass") is True and item.get("observed") == expected_identity for item in identities.values())
    valid = (
        result.get("schema_version") == "c05-phase0-probe-result-v1"
        and plan.get("run_id") == PATCH_COMPAT_ROOT.name
        and rpc_methods == ["get_state", "get_state"]
        and isinstance(checks, Mapping) and len(checks) == 13 and all(value is True for value in checks.values())
        and observed_versions == {"node": "v22.23.2", "pi": "0.84.2"}
        and runner.runtime_version_family_compatible({"node": "v22.23.2", "pi": "0.84.1"}, observed_versions)
        and identity_ok and result.get("process_returncode") == 0 and result.get("failure") is None
    )
    if not valid:
        fail("patch compatibility zero-prompt schema evidence invalid")
    return {"versions": observed_versions, "rpc_methods": rpc_methods, "identity": expected_identity, "checks": len(checks), "manifest_sha256": sha256(manifest_path)}


def verify(freeze_commit: str | None = None) -> dict[str, Any]:
    if freeze_commit and (len(freeze_commit) != 40 or any(ch not in "0123456789abcdef" for ch in freeze_commit)):
        fail("freeze commit must be a 40-character lowercase SHA")
    if freeze_commit and subprocess.run(["git", "merge-base", "--is-ancestor", freeze_commit, "HEAD"], cwd=REPO_ROOT).returncode:
        fail("freeze commit is not an ancestor of HEAD")
    return {"pass": True, "contract": verify_contract(freeze_commit), "ledger": verify_ledger_and_raw(), "corpus": verify_corpus_and_predicate(), "package": verify_preregistration_and_helpers(), "phase0": verify_phase0(), "patch_compatibility": verify_patch_compatibility_evidence(), "freeze_commit": freeze_commit}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-commit", help="optional committed freeze SHA; verifies committed bytes too")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.freeze_commit), indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"pass": False, "error": str(exc)}))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
