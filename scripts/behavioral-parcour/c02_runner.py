#!/usr/bin/env python3
"""Fresh c02 OFF/ON supersession-guard runner; imports no live process on load."""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c01_runner as c01
import phase05_runner as p

REPO_ROOT = p.REPO_ROOT
CORPUS_PATH = HERE / "c02-supersession-corpus.json"
CONTRACT_PATH = HERE / "c02-contract-files.json"
C02_PI_VERSION = "0.84.1"
C02_NODE_VERSION = re.compile(r"v22\.23\.\d+\Z")
GUARD_REASON = "Explicit durable-state supersession guard"


def sha256_file(path: Path) -> str:
    return p.sha256_file(path)


def load_corpus() -> Dict[str, Dict[str, Any]]:
    data = json.loads(CORPUS_PATH.read_text())
    if data.get("schema_version") != "c02-supersession-corpus-v1":
        raise ValueError("unsupported c02 corpus schema")
    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 8:
        raise ValueError("c02 corpus must contain exactly eight fixtures")
    mapped = {item.get("id"): item for item in fixtures if isinstance(item, dict) and isinstance(item.get("id"), str)}
    if len(mapped) != 8 or set(mapped) != {item["id"] for item in fixtures}:
        raise ValueError("c02 corpus fixture IDs must be unique")
    if sum(item.get("kind") == "positive" for item in mapped.values()) != 4:
        raise ValueError("c02 corpus must contain four positive fixtures")
    if sum(item.get("kind") == "control" for item in mapped.values()) != 4:
        raise ValueError("c02 corpus must contain four controls")
    for item in mapped.values():
        if not isinstance(item.get("target"), str) or Path(item["target"]).is_absolute() or ".." in Path(item["target"]).parts:
            raise ValueError("c02 fixture target is invalid")
        if not isinstance(item.get("before"), str) or not isinstance(item.get("prompts"), list) or len(item["prompts"]) != 3:
            raise ValueError("c02 fixture must provide before text and exactly three prompts")
    return mapped


FIXTURES = load_corpus()
FIXTURE_ORDER = list(FIXTURES)
RUN_SPECS = [
    {"run_id": f"c02-{arm}-r{repetition}-{fixture_id}", "arm": arm, "repetition": repetition, "fixture_id": fixture_id}
    for repetition in (1, 2, 3)
    for fixture_id in FIXTURE_ORDER
    for arm in ("off", "on")
]
RUN_BY_ID = {item["run_id"]: item for item in RUN_SPECS}


def guard_fired(events: List[Dict[str, Any]]) -> bool:
    return any(event.get("type") == "injection_complete" and event.get("governor_reason") == GUARD_REASON for event in events)


def continuity_passes(fixture: Dict[str, Any], final_text: str) -> bool:
    if fixture.get("kind") != "positive":
        return True
    lower = final_text.lower()
    current = all(marker.lower() in lower for marker in fixture.get("current_markers", []))
    historical = all(
        marker.lower() in lower and any(word in lower[max(0, lower.find(marker.lower()) - 100): lower.find(marker.lower()) + len(marker) + 100] for word in ("supersed", "histor", "replac", "former", "previous", "retired", "migrated"))
        for marker in fixture.get("historical_markers", [])
    )
    return current and historical


def verify_contract(expected_sha256: str) -> Dict[str, Any]:
    if sha256_file(CONTRACT_PATH) != expected_sha256:
        raise RuntimeError("c02 contract SHA-256 mismatch")
    data = json.loads(CONTRACT_PATH.read_text())
    if data.get("schema_version") != "c02-contract-files-v1" or not isinstance(data.get("files"), list):
        raise RuntimeError("c02 contract schema invalid")
    paths: set[str] = set()
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise RuntimeError("c02 contract entry invalid")
        rel = item["path"]
        if not isinstance(rel, str) or rel in paths or rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError("c02 contract path invalid")
        paths.add(rel)
        target = REPO_ROOT / rel
        if not target.is_file() or sha256_file(target) != item["sha256"]:
            raise RuntimeError(f"c02 contract file mismatch: {rel}")
    if not paths:
        raise RuntimeError("c02 contract has no files")
    return data


def command_for(workspace: Path, sessions: Path, run_id: str) -> List[str]:
    return c01.build_pi_command(run_id, 1, "active", workspace, sessions)


class C02Runner(c01.C01Runner):
    def __init__(self, spec: Dict[str, Any], product_commit: str, runner_sha256: str, corpus_sha256: str, contract_sha256: str, review_session_sha256: str) -> None:
        super().__init__("pre-stage-c", "A1", spec["run_id"], "active", spec["repetition"], "0" * 40, "0" * 40, "0" * 64, runner_sha256, contract_sha256, product_commit)
        self.spec = spec
        self.fixture = FIXTURES[spec["fixture_id"]]
        self.corpus_sha256 = corpus_sha256
        self.review_session_sha256 = review_session_sha256
        self.expected_runner_sha = runner_sha256
        self.expected_contract_sha = contract_sha256
        self.product_commit = product_commit
        self.fixture_before: Optional[Path] = None

    def _validate_frozen_inputs(self) -> None:
        if self.spec != RUN_BY_ID.get(self.run_id):
            raise RuntimeError("c02 run ID does not match frozen schedule")
        for value, length, label in ((self.product_commit, 40, "product commit"), (self.expected_runner_sha, 64, "runner sha"), (self.corpus_sha256, 64, "corpus sha"), (self.expected_contract_sha, 64, "contract sha"), (self.review_session_sha256, 64, "review session sha")):
            if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
                raise RuntimeError(f"invalid {label}")
        head = p.cmd_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)["output"].strip()
        if head != self.product_commit:
            raise RuntimeError("product commit mismatch before materialization")
        if sha256_file(Path(__file__).resolve()) != self.expected_runner_sha:
            raise RuntimeError("runner SHA mismatch before materialization")
        if sha256_file(CORPUS_PATH) != self.corpus_sha256:
            raise RuntimeError("corpus SHA mismatch before materialization")
        review = REPO_ROOT / "docs" / "c02-evidence" / "independent-review-8081-twins-session.jsonl"
        if not review.is_file() or sha256_file(review) != self.review_session_sha256:
            raise RuntimeError("review session evidence mismatch before materialization")
        verify_contract(self.expected_contract_sha)
        pi = p.cmd_output(["pi", "--version"])
        node = p.cmd_output(["node", "--version"])
        if pi["exit_code"] != 0 or pi["output"].strip() != C02_PI_VERSION:
            raise RuntimeError("Pi identity mismatch before materialization")
        if node["exit_code"] != 0 or C02_NODE_VERSION.fullmatch(node["output"].strip()) is None:
            raise RuntimeError("Node identity mismatch before materialization")

    def _guard_existing_paths(self) -> None:
        for path in (self.tmp_root, self.workspace, self.evidence_dir):
            if path.exists():
                raise FileExistsError(f"refusing existing c02 target: {path}")

    def _materialize_workspace(self) -> None:
        self.tmp_root.mkdir(parents=True)
        self.workspace.mkdir()
        self.sessions_dir.mkdir()
        target = self.workspace / self.fixture["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.fixture["before"])
        settings = self.workspace / ".pi" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"consortium": {"enabled": True, "governorMode": "smart_extractor", "stateSupersessionGuard": self.spec["arm"] == "on"}}, indent=2) + "\n")
        self.fixture_before = self.tmp_root / "fixture-before"
        self.fixture_before.mkdir()
        shutil.copy2(target, self.fixture_before / self.fixture["target"])

    def _build_manifest(self) -> Dict[str, Any]:
        command = command_for(self.workspace, self.sessions_dir, self.run_id)
        pi = p.cmd_output(["pi", "--version"])
        node = p.cmd_output(["node", "--version"])
        status = p.cmd_output(["git", "status", "--short"], cwd=REPO_ROOT)
        checks = {
            "schedule": self.spec == RUN_BY_ID.get(self.run_id),
            "product_commit": p.cmd_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)["output"].strip() == self.product_commit,
            "runner_sha256": sha256_file(Path(__file__).resolve()) == self.expected_runner_sha,
            "corpus_sha256": sha256_file(CORPUS_PATH) == self.corpus_sha256,
            "contract": bool(verify_contract(self.expected_contract_sha)),
            "review_session_sha256": sha256_file(REPO_ROOT / "docs" / "c02-evidence" / "independent-review-8081-twins-session.jsonl") == self.review_session_sha256,
            "pi_version": pi["exit_code"] == 0 and pi["output"].strip() == C02_PI_VERSION,
            "node_version": node["exit_code"] == 0 and C02_NODE_VERSION.fullmatch(node["output"].strip()) is not None,
            "guard_setting": self.spec["arm"] == (json.loads((self.workspace / ".pi" / "settings.json").read_text())["consortium"]["stateSupersessionGuard"] and "on" or "off"),
            "exact_model": command[command.index("--provider") + 1] == p.MODEL_PROVIDER and command[command.index("--model") + 1] == p.MODEL_ID and command[command.index("--thinking") + 1] == p.THINKING_LEVEL,
        }
        self.manifest = {
            "schema_version": "c02-run-manifest-v1", "run_id": self.run_id, "arm": self.spec["arm"], "repetition": self.spec["repetition"], "fixture_id": self.fixture["id"], "fixture_kind": self.fixture["kind"],
            "started_at": datetime.datetime.utcnow().isoformat() + "Z", "workspace": str(self.workspace), "runtime_root": str(self.runtime_root), "argv": command,
            "expected": {"product_commit": self.product_commit, "runner_sha256": self.expected_runner_sha, "corpus_sha256": self.corpus_sha256, "contract_sha256": self.expected_contract_sha, "review_session_sha256": self.review_session_sha256},
            "runtime_versions": {"pi_cli": pi, "node_cli": node}, "repository_status": status, "identity_checks": checks,
        }
        return self.manifest

    def _validate_all(self) -> List[p.Assertion]:
        assertions: List[p.Assertion] = []
        def add(identifier: str, passed: bool, details: str) -> None:
            item = p.Assertion(identifier, details); item.passed = passed; item.details = details; item.evidence = [{"file": "result.json", "assertion": identifier}]; assertions.append(item)
        rc = self.process_returncode if self.process_returncode is not None else -1
        add("C02-process", rc == 0, f"returncode={rc}")
        initial = self.responses.get("get_state", {}).get("data", {})
        final = self.responses.get("state_final", {}).get("data", {})
        for identifier, validator in (("C02-provider", p.validate_provider_exact), ("C02-model", p.validate_model_exact), ("C02-thinking", p.validate_thinking_off)):
            one, two = validator(initial), validator(final)
            add(identifier, one.passed and two.passed, f"initial={one.details}; final={two.details}")
        prompts = [item for item in self.outgoing_commands if item.get("type") == "prompt"]
        add("C02-prompts", [item.get("message") for item in prompts] == self.fixture["prompts"], f"count={len(prompts)}")
        add("C02-protocol", not self.protocol_errors, f"errors={self.protocol_errors}")
        identities = self.manifest.get("identity_checks", {})
        add("C02-identities", bool(identities) and all(value is True for value in identities.values()), f"checks={identities}")
        starts = [event for event in self.consortium_events if event.get("type") == "deliberation_start"]
        local_trace = bool(starts) and all(event.get("provider") == p.MODEL_PROVIDER and event.get("modelId") == p.MODEL_ID for event in starts)
        add("C02-trace-identity", local_trace, f"deliberation_starts={len(starts)}")
        fired = guard_fired(self.consortium_events)
        expected_guard = self.spec["arm"] == "on" and self.fixture["kind"] == "positive"
        add("C02-guard", fired == expected_guard, f"expected={expected_guard}; observed={fired}")
        target = self.workspace / self.fixture["target"]
        text = target.read_text() if target.exists() else ""
        continuity = continuity_passes(self.fixture, text)
        add("C02-continuity", continuity, f"positive={self.fixture['kind'] == 'positive'}; continuity={continuity}")
        return assertions

    def _harvest(self, result: Dict[str, Any]) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, default=str) + "\n")
        for source, target_name in ((self.fixture_before, "fixture-before"), (self.workspace, "fixture-after")):
            target_root = self.evidence_dir / target_name
            target_root.mkdir()
            if source:
                for file in source.rglob("*"):
                    if file.is_file():
                        target = target_root / file.relative_to(source); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, target)
        for source_name in ("live-boundary.json", "rpc-events.jsonl"):
            source = self.tmp_root / source_name
            if source.exists(): shutil.copy2(source, self.evidence_dir / source_name)
        (self.evidence_dir / "raw-incoming.jsonl").write_text("\n".join(self.raw_incoming) + ("\n" if self.raw_incoming else ""))
        (self.evidence_dir / "outgoing-commands.jsonl").write_text("\n".join(json.dumps(item) for item in self.outgoing_records) + ("\n" if self.outgoing_records else ""))
        (self.evidence_dir / "combined-directional.jsonl").write_text("\n".join(json.dumps(item) for item in self.directional_records) + ("\n" if self.directional_records else ""))
        (self.evidence_dir / "rpc-stderr.log").write_text("\n".join(self.stderr_lines) + ("\n" if self.stderr_lines else ""))
        for source_root, target_name in ((self.sessions_dir, "sessions"), (self.workspace / ".pi" / "consortium", "consortium")):
            target_root = self.evidence_dir / target_name; target_root.mkdir()
            if source_root.exists():
                for file in source_root.rglob("*"):
                    if file.is_file():
                        target = target_root / file.relative_to(source_root); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, target)
        for key in ("state_final", "entries_final", "stats_final", "text_final"):
            if key in self.responses: (self.evidence_dir / f"{key}.json").write_text(json.dumps(self.responses[key], indent=2, default=str) + "\n")
        (self.evidence_dir / "result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
        self._refresh_evidence_manifest()

    def _refresh_evidence_manifest(self) -> None:
        files = [{"path": str(file.relative_to(self.evidence_dir)), "sha256": sha256_file(file), "size": file.stat().st_size} for file in sorted(self.evidence_dir.rglob("*")) if file.is_file() and file.name != "evidence-manifest.json"]
        (self.evidence_dir / "evidence-manifest.json").write_text(json.dumps({"run_id": self.run_id, "files": files, "coverage": {"total_files": len(files), "total_bytes": sum(item["size"] for item in files)}}, indent=2) + "\n")

    def run(self) -> Dict[str, Any]:
        saved = c01.PROMPTS
        c01.PROMPTS = self.fixture["prompts"]
        try:
            result = super().run()
        finally:
            c01.PROMPTS = saved
        assertions = result.get("assertions", [])
        result["c02"] = {"fixture_id": self.fixture["id"], "fixture_kind": self.fixture["kind"], "guard_fired": guard_fired(self.consortium_events), "continuity_passes": continuity_passes(self.fixture, (self.workspace / self.fixture["target"]).read_text() if (self.workspace / self.fixture["target"]).exists() else ""), "tool_call_count": sum(event.get("type") == "tool_execution_start" for event in self.rpc_events)}
        result["pass"] = all(item.get("pass") for item in assertions)
        if self.harvest_allowed:
            (self.evidence_dir / "result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
            self._refresh_evidence_manifest()
        return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="c02 fresh supersession guard runner")
    parser.add_argument("--run-id", required=True, choices=sorted(RUN_BY_ID))
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--review-session-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    runner = C02Runner(RUN_BY_ID[args.run_id], args.product_commit, args.runner_sha256, args.corpus_sha256, args.contract_sha256, args.review_session_sha256)
    result = runner.preflight() if args.preflight_only else runner.run()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
