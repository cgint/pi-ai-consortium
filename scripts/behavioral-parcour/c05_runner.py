#!/usr/bin/env python3
"""Fresh c05 prospective runner.  Importing it has no side effects and never launches Pi."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c05_phase0 as phase0
import c05_scorer
import phase05_runner as base

REPO_ROOT = base.REPO_ROOT
CORPUS_PATH = HERE / "c05-supersession-corpus.json"
PHASE0_PATH = REPO_ROOT / "docs/c05-evidence/phase0-capability-b/result.json"
RAW_ROOT = REPO_ROOT / "docs/c05-raw"
RUN_ROOT = REPO_ROOT / ".parcour-runs"
CONTRACT_PATH = HERE / "c05-contract-files.json"
REVIEW_PATH = REPO_ROOT / "docs/c05-evidence/independent-review.json"
LEDGER_PATH = REPO_ROOT / "docs/c05-evidence/raw-publication-ledger.json"
PHASE0_SHA256 = "f9a90f1a93f07f64d2da76602323906444d333ced4ccc20296439e3a537aa76f"
RECORDED_PI_VERSION, RECORDED_NODE_VERSION = "0.84.1", "v22.23.2"
PI_VERSION_FAMILY, NODE_VERSION_FAMILY = (0, 84), (22,)
MODEL_PROVIDER, MODEL_ID, THINKING = phase0.MODEL_PROVIDER, phase0.MODEL_ID, phase0.THINKING_LEVEL
MODEL_REF = phase0.MODEL_REF
GUARD_REASON = "Explicit durable-state supersession guard"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_corpus() -> dict[str, dict[str, Any]]:
    data = json.loads(CORPUS_PATH.read_text())
    fixtures = data.get("fixtures")
    if data.get("schema_version") != "c05-supersession-corpus-v1" or not isinstance(fixtures, list) or len(fixtures) != 8:
        raise ValueError("c05 corpus must be exactly eight fixtures")
    result = {x.get("id"): x for x in fixtures if isinstance(x, dict) and isinstance(x.get("id"), str)}
    if len(result) != 8 or sum(x.get("kind") == "positive" for x in result.values()) != 4 or sum(x.get("kind") == "control" for x in result.values()) != 4:
        raise ValueError("c05 corpus requires unique four-positive/four-control fixtures")
    for fixture in result.values():
        target = fixture.get("target")
        if not isinstance(target, str) or Path(target).is_absolute() or ".." in Path(target).parts or not isinstance(fixture.get("before"), str) or not isinstance(fixture.get("prompts"), list) or len(fixture["prompts"]) != 3:
            raise ValueError("invalid c05 fixture")
    return result

FIXTURES = load_corpus()
FIXTURE_ORDER = list(FIXTURES)
SMOKE_SPECS = [{"run_id": f"c05-smoke-on-{fixture_id}", "arm": "on", "fixture_id": fixture_id, "smoke": True} for fixture_id in FIXTURE_ORDER]
RUN_SPECS = [{"run_id": f"c05-{arm}-r{rep}-{fixture_id}", "arm": arm, "repetition": rep, "fixture_id": fixture_id, "smoke": False} for rep in (1, 2, 3) for fixture_id in FIXTURE_ORDER for arm in ("off", "on")]
ALL_SPECS = SMOKE_SPECS + RUN_SPECS
BY_ID = {s["run_id"]: s for s in ALL_SPECS}


def run_paths(specs: Sequence[Mapping[str, Any]]) -> list[Path]:
    return [path for spec in specs for path in (RUN_ROOT / str(spec["run_id"]), RAW_ROOT / str(spec["run_id"]))]


def raw_destination_conflict(path: Path) -> bool:
    return path.exists() and (not path.is_dir() or {child.name for child in path.iterdir()} != {".gitkeep"})


def build_child_env(ambient: Mapping[str, str]) -> dict[str, str]:
    return phase0.build_child_env(ambient)


def build_pi_command(workspace: Path, sessions: Path, run_id: str) -> list[str]:
    return ["pi", "--mode", "rpc", "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-extensions", "--tools", "read,edit,grep,find,ls", "-e", str(base.PROVIDER_EXT), "-e", str(base.CONSORTIUM_EXT), "-e", str(base.FOCUS_EXT), "--provider", MODEL_PROVIDER, "--model", MODEL_ID, "--thinking", THINKING, "--dm-off", "--write-guard", str(workspace), "--approve", "--session-dir", str(sessions), "--name", run_id]


def current_runtime_versions() -> dict[str, str]:
    """Read exact runtime strings for provenance; compatibility is evaluated separately."""
    return {
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "pi": subprocess.check_output(["pi", "--version"], text=True).strip(),
    }


def runtime_version_family_compatible(accepted: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """Accept patch drift only within frozen Pi 0.84.* and Node 22.* families."""
    accepted_node = phase0.parse_version(str(accepted.get("node", "")), prefix="v")
    accepted_pi = phase0.parse_version(str(accepted.get("pi", "")))
    current_node = phase0.parse_version(str(current.get("node", "")), prefix="v")
    current_pi = phase0.parse_version(str(current.get("pi", "")))
    return bool(
        accepted_node and accepted_pi and current_node and current_pi
        and accepted_node[:1] == current_node[:1] == NODE_VERSION_FAMILY
        and accepted_pi[:2] == current_pi[:2] == PI_VERSION_FAMILY
    )


def validate_runtime_gate(accepted: Mapping[str, Any], workspace: Path, sessions: Path, run_id: str, versions: Mapping[str, Any] | None = None) -> bool:
    """Independently recheck current runtime inputs against Phase0-B's plan."""
    plan = accepted.get("plan", {})
    command, child, hashes = plan.get("command"), plan.get("child_environment"), plan.get("extension_hashes")
    current = build_pi_command(workspace, sessions, run_id)
    selected_child = {key: build_child_env(dict(os.environ)).get(key) for key in ("CONSORTIUM_MODEL", "PI_SKIP_VERSION_CHECK")}
    try:
        versions = dict(versions) if versions is not None else current_runtime_versions()
        accepted_versions = accepted.get("version_check", {}).get("observed", {})
        extensions_ok = isinstance(hashes, Mapping) and len(hashes) == 3 and all(isinstance(path, str) and re.fullmatch(r"[0-9a-f]{64}", str(digest)) and Path(path).is_file() and sha256_file(Path(path)) == digest for path, digest in hashes.items())
        # Compare stable runtime identity; probe-only tools and run-specific paths are intentionally different.
        def command_identity(argv: Any) -> list[str] | None:
            if not isinstance(argv, list):
                return None
            ignored = {"--tools", "--write-guard", "--session-dir", "--name"}
            return [str(item) for index, item in enumerate(argv) if not (argv[index - 1] in ignored if index else False) and item not in ignored]
        confined = all(str(path).startswith(str(REPO_ROOT) + os.sep) for path in (workspace, sessions))
        return runtime_version_family_compatible(accepted_versions, versions) and extensions_ok and command_identity(command) == command_identity(current) and confined and child == selected_child
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return False


def validate_phase0(path: Path, expected_sha256: str):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Phase 0 SHA-256 must be full lowercase hex")
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise RuntimeError("accepted Phase 0 result SHA/path mismatch")
    data = json.loads(path.read_text())
    checks = data.get("checks", {})
    observed = data.get("version_check", {}).get("observed", {})
    identities = data.get("identity", {})
    valid = data.get("pass") is True and all(checks.values()) and observed == {"pi": RECORDED_PI_VERSION, "node": RECORDED_NODE_VERSION} and all(x.get("pass") is True for x in identities.values())
    if not valid:
        raise RuntimeError("accepted Phase 0 result identity/version checks failed")
    return data


def validate_contract(path: Path, expected_sha256: str, freeze_commit: str) -> dict[str, Any]:
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise RuntimeError("c05 contract SHA/path mismatch")
    data = json.loads(path.read_text())
    if not re.fullmatch(r"[0-9a-f]{40}", freeze_commit) or "freeze_commit" in data or not isinstance(data.get("files"), list) or not data["files"]:
        raise RuntimeError("c05 contract malformed or self-referential")
    if subprocess.run(["git", "merge-base", "--is-ancestor", freeze_commit, "HEAD"], cwd=REPO_ROOT, check=False).returncode:
        raise RuntimeError("c05 freeze is not an ancestor")
    for item in data["files"]:
        rel, digest = item.get("path"), item.get("sha256") if isinstance(item, dict) else (None, None)
        if not isinstance(rel, str) or not re.fullmatch(r"[0-9a-f]{64}", str(digest)) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise RuntimeError("invalid c05 contract entry")
        target = REPO_ROOT / rel
        frozen = subprocess.run(["git", "show", f"{freeze_commit}:{rel}"], cwd=REPO_ROOT, capture_output=True)
        if not target.is_file() or sha256_file(target) != digest or frozen.returncode or hashlib.sha256(frozen.stdout).hexdigest() != digest:
            raise RuntimeError("current/frozen c05 contract mismatch")
    return data


def validate_review(path: Path, expected_sha256: str, freeze_at: str, preflight_at: str) -> dict[str, Any]:
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise RuntimeError("c05 review SHA/path mismatch")
    data = json.loads(path.read_text())
    try:
        parse = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        timed = parse(freeze_at) < parse(data["timestamp"]) <= parse(preflight_at)
        raw_rel = Path(data["raw_session_path"])
        if raw_rel.is_absolute() or ".." in raw_rel.parts:
            raise ValueError("review raw session path must be repo-relative")
        raw = REPO_ROOT / raw_rel
        raw.resolve().relative_to(REPO_ROOT.resolve())
        session = raw.read_bytes()
        raw_ok = raw.is_file() and hashlib.sha256(session).hexdigest() == data["raw_session_sha256"]
        events = [json.loads(line) for line in session.decode().splitlines() if line.strip()]
        info = next(event for event in events if event.get("type") == "session_info")
        models = [event for event in events if event.get("type") == "model_change"]
        thinking = [event for event in events if event.get("type") == "thinking_level_change"]
        assistants = [event for event in events if event.get("type") == "message" and isinstance(event.get("message"), Mapping) and event["message"].get("role") == "assistant"]
        assistant = assistants[-1]
        text = "\n".join(part.get("text", "") for part in assistant["message"].get("content", []) if isinstance(part, Mapping) and part.get("type") == "text")
        structured = (isinstance(info.get("name"), str) and info["name"].startswith("c05-8081-twins") and info.get("timestamp") == data["timestamp"]
            and bool(models) and bool(thinking)
            and all(event.get("provider") == MODEL_PROVIDER and event.get("modelId") == MODEL_ID for event in models)
            and all(event.get("thinkingLevel") == THINKING for event in thinking)
            and bool(re.search(r"(?:^|\n)\s*(?:HEADLINE:\s*PASS\b|\*\*PASS\*\*)", text, re.I))
            and bool(re.search(r"(?:^|\n)\s*BLOCKER\s*:\s*(?:None|No)\b", text, re.I)))
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError): timed = raw_ok = structured = False
    if data.get("pass") is not True or data.get("blockers") not in ([], None) or not timed or not raw_ok or not structured:
        raise RuntimeError("c05 review lacks timed raw-session-backed structured PASS")
    return data


def _ledger_data(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    if not path.is_file() or (expected_sha256 is not None and sha256_file(path) != expected_sha256):
        raise RuntimeError("c05 ledger SHA/path mismatch")
    data = json.loads(path.read_text())
    ids = [s["run_id"] for s in ALL_SPECS]
    records = data.get("runs")
    if data.get("schema_version") != "c05-raw-publication-ledger-v1" or not isinstance(records, list) or len(records) != 56 or [x.get("run_id") for x in records] != ids:
        raise RuntimeError("c05 ledger must contain schema-bound 56 ordered runs")
    return data


def _verify_result_evidence(result_path: Path, expected_run_id: str) -> dict[str, Any]:
    if not result_path.is_file():
        raise RuntimeError("c05 result evidence is missing")
    result = json.loads(result_path.read_text())
    manifest_path = result_path.parent / "evidence-manifest.json"
    if result.get("run_id") != expected_run_id or not manifest_path.is_file():
        raise RuntimeError("c05 result evidence identity/manifest mismatch")
    manifest = json.loads(manifest_path.read_text())
    files = {item.get("path"): item for item in manifest.get("files", []) if isinstance(item, Mapping) and isinstance(item.get("path"), str)}
    if not any(name.startswith("sessions/") and name.endswith(".jsonl") for name in files) or not any(name.startswith("consortium/") and name.endswith(".jsonl") for name in files):
        raise RuntimeError("c05 evidence manifest lacks session/consortium logs")
    if not files or not all(isinstance(item.get("sha256"), str) and isinstance(item.get("size"), int) and (result_path.parent / name).is_file() and sha256_file(result_path.parent / name) == item["sha256"] and (result_path.parent / name).stat().st_size == item["size"] for name, item in files.items()):
        raise RuntimeError("c05 evidence manifest hash/size mismatch")
    return result


def _atomic_json_write(path: Path, data: Mapping[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists(): temp.unlink()


def consume_ledger_record(ledger_path: Path, expected_sha: str, run_id: str, result_path: Path, runner_exit: int) -> tuple[str, dict[str, Any]]:
    """Atomically consume one hash-pinned ledger record after valid raw harvest."""
    ledger = _ledger_data(ledger_path, expected_sha)
    records = ledger["runs"]
    record = next((item for item in records if item.get("run_id") == run_id), None)
    if record is None or record.get("status") != "unconsumed":
        raise RuntimeError("c05 ledger record is absent or already consumed")
    result = _verify_result_evidence(result_path, run_id)
    record.update({"status": "consumed", "runner_exit": runner_exit, "result_sha256": sha256_file(result_path), "failed_assertions": result.get("failed_assertions", []), "consumed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    _atomic_json_write(ledger_path, ledger)
    return sha256_file(ledger_path), ledger


def build_smoke_decision(ledger_path: Path, output_path: Path) -> dict[str, Any]:
    """Build, but do not commit or execute from, the deterministic smoke decision."""
    ledger = _ledger_data(ledger_path)
    records = ledger["runs"]
    if any(record.get("status") != "consumed" for record in records[:8]) or any(record.get("status") != "unconsumed" for record in records[8:]):
        raise RuntimeError("c05 smoke decision requires exactly eight consumed smoke records")
    results = []
    for record, spec in zip(records[:8], SMOKE_SPECS):
        result_path = REPO_ROOT / str(record["raw_directory"]) / "result.json"
        result = _verify_result_evidence(result_path, spec["run_id"])
        if record.get("result_sha256") != sha256_file(result_path):
            raise RuntimeError("c05 consumed ledger result SHA mismatch")
        results.append({key: result.get(key) for key in ("run_id", "fixture_id", "raw_valid", "failed_assertions", "identity_valid", "process_valid", "prompts_delivered", "guard_fired", "continuity", "control_regression")} | {"result_sha256": record["result_sha256"]})
    decision = {"schema_version": "c05-smoke-decision-v1", "ledger_sha256": sha256_file(ledger_path), "matrix_ready": smoke_transition(results), "results": results}
    _atomic_json_write(output_path, decision)
    return decision


def validate_ledger(path: Path, expected_sha256: str, specs: Sequence[Mapping[str, Any]], *, require_all_unconsumed: bool) -> dict[str, Any]:
    data = _ledger_data(path, expected_sha256)
    ids = [s["run_id"] for s in ALL_SPECS]
    records = data["runs"]
    current = {s["run_id"] for s in specs}
    for record, run_id in zip(records, ids):
        raw = REPO_ROOT / f"docs/c05-raw/{run_id}"
        unconsumed = record.get("status") == "unconsumed"
        if record.get("raw_directory") != f"docs/c05-raw/{run_id}" or (require_all_unconsumed and not unconsumed) or (run_id in current and not unconsumed):
            raise RuntimeError("c05 ledger destination or consumption mismatch")
        if unconsumed:
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str((raw / ".gitkeep").relative_to(REPO_ROOT))], cwd=REPO_ROOT, capture_output=True).returncode == 0
            if not (raw / ".gitkeep").is_file() or not tracked:
                raise RuntimeError("c05 unconsumed ledger record lacks tracked placeholder")
        else:
            result = raw / "result.json"
            if not result.is_file() or not isinstance(record.get("result_sha256"), str) or sha256_file(result) != record["result_sha256"]:
                raise RuntimeError("c05 consumed ledger result SHA/path mismatch")
    return data


def governor_input_valid(events: Sequence[Mapping[str, Any]], arm: str, prompt: str) -> bool:
    """Require governor input for the second (state-changing) human turn only."""
    active = False
    for event in events:
        if event.get("type") == "turn_start":
            active = event.get("input") == prompt
        elif active and event.get("type") == "governor_input":
            return event.get("state_supersession_guard") is (arm == "on") and event.get("state_supersession_guard_source") == "workspace_settings" and isinstance(event.get("current_human_turn_length"), int) and event["current_human_turn_length"] == len(prompt)
    return False


def guard_fired(events: Sequence[Mapping[str, Any]], second_prompt: str | None = None) -> bool:
    """Count only guard telemetry in the second human turn, before the next turn."""
    active = second_prompt is None
    for event in events:
        if event.get("type") == "turn_start":
            if active:
                return False
            active = event.get("input") == second_prompt
        elif active and event.get("type") in ("injection_complete", "injection_skipped") and (event.get("reason") == GUARD_REASON or event.get("governor_reason") == GUARD_REASON):
            return True
    return False


def control_regression(before: str, final_text: str) -> bool:
    """Return true when a control loses its pre-existing identity or stable constraint."""
    patterns = (
        r"YAML changelog entries",
        r"legacy-yaml-approval",
        r"YAML release notes",
        r"yaml-state-v1",
    )
    identities = [pattern for pattern in patterns if re.search(pattern, before, re.IGNORECASE)]
    if len(identities) != 1:
        raise ValueError("control before text must contain exactly one known active identity")
    matches = list(re.finditer(identities[0], final_text, re.IGNORECASE))
    # Determine status from the identity's own current clause/line, not nearby history.
    active = any(not re.search(r"\b(historical|supersed(?:ed)?|retired|migrated)\b", final_text[final_text.rfind("\n", 0, match.start()) + 1:final_text.find("\n", match.end()) if final_text.find("\n", match.end()) >= 0 else len(final_text)], re.IGNORECASE) for match in matches)
    return not (active and re.search(r"RELEASE_STREAM\s*=\s*stable", final_text, re.IGNORECASE))


def smoke_transition(results: Sequence[Mapping[str, Any]]) -> bool:
    if len(results) != 8 or [r.get("run_id") for r in results] != [s["run_id"] for s in SMOKE_SPECS]: return False
    positives = [r for r in results if FIXTURES[r.get("fixture_id")].get("kind") == "positive"]
    controls = [r for r in results if FIXTURES[r.get("fixture_id")].get("kind") == "control"]
    required = ("identity_valid", "raw_valid", "process_valid", "continuity", "control_regression")
    return all(all(key in r for key in required) and r.get("prompts_delivered") == 3 and r.get("identity_valid") and r.get("raw_valid") and r.get("process_valid") for r in results) and len(positives) == len(controls) == 4 and all(r.get("guard_fired") is True and r.get("continuity") is True for r in positives) and all(r.get("guard_fired") is False and r.get("control_regression") is False for r in controls)


def validate_smoke_decision(path: Path, expected_sha256: str, ledger: Mapping[str, Any], *, repo_root: Path = REPO_ROOT, raw_root: Path | None = None) -> bool:
    """A matrix run is authorized only by the committed, hash-pinned smoke decision."""
    if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or sha256_file(path) != expected_sha256:
        return False
    raw_root = raw_root or repo_root / "docs/c05-raw"
    try:
        if subprocess.run(["git", "ls-files", "--error-unmatch", str(path.relative_to(repo_root))], cwd=repo_root, capture_output=True).returncode:
            return False
        decision = json.loads(path.read_text())
        results = decision["results"]
        if len(results) != 8 or [result.get("run_id") for result in results] != [spec["run_id"] for spec in SMOKE_SPECS]:
            return False
        for result in results:
            raw = raw_root / result["run_id"]
            result_path, manifest_path = raw / "result.json", raw / "evidence-manifest.json"
            if not result_path.is_file() or sha256_file(result_path) != result.get("result_sha256") or not manifest_path.is_file():
                return False
            manifest = json.loads(manifest_path.read_text())
            files = {item.get("path"): item for item in manifest.get("files", []) if isinstance(item, Mapping)}
            if not any(name.startswith("sessions/") and name.endswith(".jsonl") for name in files) or not any(name.startswith("consortium/") and name.endswith(".jsonl") for name in files):
                return False
            if not all(isinstance(item.get("sha256"), str) and isinstance(item.get("size"), int) and (raw / name).is_file() and sha256_file(raw / name) == item["sha256"] and (raw / name).stat().st_size == item["size"] for name, item in files.items()):
                return False
            if result.get("raw_valid") is not True or result.get("failed_assertions"):
                return False
        return decision.get("matrix_ready") is True and matrix_ready(results, ledger)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def matrix_ready(smoke_results: Sequence[Mapping[str, Any]], ledger: Mapping[str, Any]) -> bool:
    records = ledger.get("runs", [])
    return smoke_transition(smoke_results) and isinstance(records, list) and len(records) == 56 and all(record.get("status") == "consumed" for record in records[:8]) and all(record.get("status") == "unconsumed" and not raw_destination_conflict(REPO_ROOT / record.get("raw_directory", "")) for record in records[8:])


MANDATORY_STOP_ASSERTIONS = frozenset({"C05-process", "C05-identity", "C05-preflight", "C05-trace", "C05-protocol", "C05-prompts", "C05-governor-input", "C05-confinement", "C05-raw-session", "C05-harvest"})
BEHAVIORAL_CONTINUE_ASSERTIONS = frozenset({"C05-guard", "C05-continuity", "C05-smoke-transition"})


def exit_class(assertions: Sequence[Mapping[str, Any]]) -> int:
    """Return 2 for mandatory-stop failure, 1 for behavioral failure, else 0."""
    failed = {str(x.get("id")) for x in assertions if x.get("pass") is not True}
    if not failed: return 0
    return 2 if failed & MANDATORY_STOP_ASSERTIONS else 1


class C05Sequencer:
    """Deterministically sequence C05's two initial controls and three prompts."""
    def __init__(self, prompts: Sequence[str]) -> None:
        if len(prompts) != 3:
            raise ValueError("c05 requires exactly three prompts")
        self.prompts = list(prompts)
        self.responses: dict[str, dict[str, Any]] = {}
        self.prompts_sent = 0
        self.settles = 0
        self.final_queries = False
        self.complete = False
        self.errors: list[str] = []

    def on_event(self, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if event.get("type") == "response" and event.get("id"):
            self.responses[str(event["id"])] = dict(event)
        if self.prompts_sent == 0 and {"get_state", "get_commands"}.issubset(self.responses):
            if all(self.responses[key].get("success") is True for key in ("get_state", "get_commands")):
                actions.append({"id": "prompt_0", "type": "prompt", "message": self.prompts[0]})
                self.prompts_sent = 1
            elif not self.errors:
                self.errors.append("initial response unsuccessful")
        if event.get("type") == "agent_settled":
            if self.prompts_sent == 0 or self.settles >= self.prompts_sent:
                self.errors.append("unexpected agent_settled ordering")
            else:
                self.settles += 1
                if self.settles < len(self.prompts):
                    index = self.settles
                    actions.append({"id": f"prompt_{index}", "type": "prompt", "message": self.prompts[index]})
                    self.prompts_sent += 1
                elif not self.final_queries:
                    actions.extend([
                        {"id": "state_final", "type": "get_state"},
                        {"id": "entries_final", "type": "get_entries"},
                        {"id": "stats_final", "type": "get_session_stats"},
                        {"id": "text_final", "type": "get_last_assistant_text"},
                    ])
                    self.final_queries = True
        if self.final_queries and {"state_final", "entries_final", "stats_final", "text_final"}.issubset(self.responses):
            self.complete = True
        return actions


class C05Runner(base.Phase05Runner):
    """C05 live runner with a fixed three-prompt RPC protocol."""
    def __init__(self, spec: Mapping[str, Any], **frozen: str) -> None:
        super().__init__(str(spec["run_id"]), int(spec.get("repetition", 0)), "0" * 40, "0" * 40, "0" * 64, frozen.get("freeze_commit", "0" * 40))
        self.spec, self.fixture, self.frozen = dict(spec), FIXTURES[str(spec["fixture_id"])], frozen
        self.runtime_root = RUN_ROOT / self.run_id
        self.tmp_root = self.runtime_root
        self.workspace, self.sessions_dir = self.runtime_root / "workspace", self.runtime_root / "sessions"
        self.evidence_dir = RAW_ROOT / self.run_id
        self.fixture_before: Path | None = None

    def preflight(self, all_targets: bool = True) -> dict[str, Any]:
        """Validate every prospective gate before any directory is created."""
        try:
            if self.spec != BY_ID.get(self.run_id): raise RuntimeError("run ID not in frozen c05 schedule")
            specs = ALL_SPECS if all_targets else [self.spec]
            conflicts = [str(p) for p in run_paths(specs) if (p.parent == RAW_ROOT and raw_destination_conflict(p)) or (p.parent != RAW_ROOT and p.exists())]
            if conflicts: raise FileExistsError(f"refusing existing c05 targets: {conflicts}")
            phase0_result = validate_phase0(PHASE0_PATH, self.frozen["phase0_sha256"])
            validate_contract(Path(self.frozen.get("contract_path", CONTRACT_PATH)), self.frozen["contract_sha256"], self.frozen["freeze_commit"])
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            freeze_at = subprocess.check_output(["git", "show", "-s", "--format=%cI", self.frozen["freeze_commit"]], cwd=REPO_ROOT, text=True).strip()
            validate_review(Path(self.frozen.get("review_path", REVIEW_PATH)), self.frozen["review_sha256"], freeze_at, now)
            ledger = validate_ledger(Path(self.frozen.get("ledger_path", LEDGER_PATH)), self.frozen["ledger_sha256"], specs, require_all_unconsumed=all_targets)
            if not self.spec.get("smoke") and not validate_smoke_decision(Path(self.frozen.get("smoke_decision_path", "")), self.frozen.get("smoke_decision_sha256", ""), ledger):
                raise RuntimeError("matrix run requires a verified committed smoke decision")
            current_versions = current_runtime_versions()
            self.manifest = {"schema_version": "c05-run-manifest-v1", "run_id": self.run_id, "workspace": str(self.workspace), "runtime_root": str(self.runtime_root), "raw_destination": f"docs/c05-raw/{self.run_id}", "argv": build_pi_command(self.workspace, self.sessions_dir, self.run_id), "child_environment": {key: build_child_env(dict(os.environ)).get(key) for key in ("CONSORTIUM_MODEL", "PI_SKIP_VERSION_CHECK")}, "runtime_versions": {"accepted_phase0": phase0_result["version_check"]["observed"], "current": current_versions}, "extension_hashes": phase0_result["plan"]["extension_hashes"], "phase0_sha256": self.frozen["phase0_sha256"], "contract_sha256": self.frozen["contract_sha256"], "review_sha256": self.frozen["review_sha256"], "ledger_sha256": self.frozen["ledger_sha256"], "freeze_commit": self.frozen["freeze_commit"], "arm": self.spec["arm"], "fixture_id": self.fixture["id"], "smoke": self.spec["smoke"], "phase0": str(PHASE0_PATH)}
            if not validate_runtime_gate(phase0_result, self.workspace, self.sessions_dir, self.run_id, current_versions):
                raise RuntimeError("current runtime inputs differ from accepted Phase0 B capabilities, identity, or compatible version families")
            return {"pass": True, "prompts_delivered": 0, "manifest": self.manifest}
        except Exception as exc:
            return {"pass": False, "prompts_delivered": 0, "exception": f"{type(exc).__name__}: {exc}", "manifest": self.manifest}

    def _materialize_workspace(self) -> None:
        self.runtime_root.mkdir(parents=True)
        self.workspace.mkdir()
        self.sessions_dir.mkdir()
        target = self.workspace / self.fixture["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.fixture["before"])
        settings, payload = phase0.settings_spec(self.workspace, self.spec["arm"] == "on")
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(phase0.serialize_settings(payload))
        persisted = json.loads(settings.read_text())
        if not phase0.validate_settings_spec(self.workspace, settings, persisted, self.spec["arm"] == "on"):
            raise RuntimeError("c05 workspace guard setting mismatch before Pi launch")
        self.manifest["workspace_guard_setting"] = persisted["consortium"]["stateSupersessionGuard"]
        self.fixture_before = self.runtime_root / "fixture-before"
        before_target = self.fixture_before / self.fixture["target"]
        before_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, before_target)

    def _spawn_pi(self, command: Sequence[str], stderr_path: Path) -> subprocess.Popen:
        stderr_handle = stderr_path.open("wb")
        proc = subprocess.Popen(
            list(command), cwd=str(self.workspace), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=stderr_handle, env=build_child_env(dict(os.environ)), start_new_session=True,
        )
        proc._stderr_handle = stderr_handle  # type: ignore[attr-defined]
        return proc

    def _run_rpc_loop(self, proc: subprocess.Popen, rpc_log_path: Path, stderr_path: Path) -> None:
        assert proc.stdin is not None and proc.stdout is not None
        buffer = b""
        total_start = time.monotonic()
        turn_start: float | None = None
        sequencer = C05Sequencer(self.fixture["prompts"])
        reported_errors = 0
        self._send(proc, {"id": "get_state", "type": "get_state"})
        self._send(proc, {"id": "get_commands", "type": "get_commands"})
        with rpc_log_path.open("wb") as rpc_log:
            while not sequencer.complete:
                if time.monotonic() - total_start > base.TIMEOUT_SECONDS * 3:
                    self.timeout_occurred = True
                    self.protocol_errors.append("Total timeout")
                    self._terminate_process_group(proc)
                    break
                if turn_start is not None and time.monotonic() - turn_start > base.TIMEOUT_SECONDS:
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
                rpc_log.write(chunk)
                rpc_log.flush()
                buffer += chunk
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
                    self.rpc_events.append(event)
                    self._record_direction("out", event)
                    if event.get("type") == "response" and event.get("id"):
                        self.responses[str(event["id"])] = event
                    actions = sequencer.on_event(event)
                    if len(sequencer.errors) > reported_errors:
                        self.protocol_errors.extend(sequencer.errors[reported_errors:])
                        reported_errors = len(sequencer.errors)
                    if sequencer.errors:
                        break
                    if event.get("type") == "agent_settled":
                        turn_start = None
                    for action in actions:
                        if action["type"] == "prompt":
                            if action["id"] == "prompt_0" and self.live_boundary_ts is None:
                                self.live_boundary_ts = dt.datetime.now(dt.timezone.utc).isoformat()
                                (self.runtime_root / "live-boundary.json").write_text(json.dumps({"run_id": self.run_id, "ts": self.live_boundary_ts}, indent=2) + "\n")
                            turn_start = time.monotonic()
                        self._send(proc, action)
                if sequencer.errors:
                    break
        if buffer.strip():
            self.protocol_errors.append("Unterminated stdout bytes")
        if not sequencer.complete and not self.timeout_occurred and not sequencer.errors:
            self.protocol_errors.append("RPC stream ended before final responses")
        try:
            proc.stdin.close()
        except Exception:
            pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._terminate_process_group(proc)
        try:
            proc._stderr_handle.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        if stderr_path.exists():
            self.stderr_lines = stderr_path.read_text(errors="replace").splitlines()
        self.process_returncode = proc.returncode

    def _validate_all(self) -> list[dict[str, Any]]:
        initial = self.responses.get("get_state", {}).get("data", {})
        final = self.responses.get("state_final", {}).get("data", {})
        def identity(response: Mapping[str, Any]) -> bool:
            return phase0.validate_executor_state(response).get("pass") is True
        prompts = [item for item in self.outgoing_commands if item.get("type") == "prompt"]
        protocol = not self.protocol_errors and all(self.responses.get(key, {}).get("success") is True for key in ("get_state", "get_commands", "state_final", "entries_final", "stats_final", "text_final"))
        traces = [event for event in self.consortium_events if event.get("type") == "deliberation_start"]
        trace = bool(traces) and all(event.get("model") == MODEL_REF and event.get("modelSource") == "CONSORTIUM_MODEL" for event in traces)
        target = self.workspace / self.fixture["target"]
        final_text = target.read_text() if target.is_file() else ""
        continuity = c05_scorer.continuity_passes(self.fixture, final_text)
        regression = control_regression(self.fixture["before"], final_text) if self.fixture["kind"] == "control" else False
        assertions = [
            {"id": "C05-process", "pass": self.process_returncode == 0},
            {"id": "C05-identity", "pass": identity(self.responses.get("get_state", {})) and identity(self.responses.get("state_final", {}))},
            {"id": "C05-prompts", "pass": [p.get("message") for p in prompts] == self.fixture["prompts"]},
            {"id": "C05-protocol", "pass": protocol},
            {"id": "C05-preflight", "pass": bool(self.manifest.get("workspace_guard_setting") is (self.spec["arm"] == "on"))},
            {"id": "C05-trace", "pass": trace},
            {"id": "C05-governor-input", "pass": governor_input_valid(self.consortium_events, self.spec["arm"], self.fixture["prompts"][1])},
            {"id": "C05-guard", "pass": guard_fired(self.consortium_events, self.fixture["prompts"][1]) is (self.spec["arm"] == "on" and self.fixture["kind"] == "positive")},
            {"id": "C05-continuity", "pass": continuity},
            {"id": "C05-control", "pass": not regression},
            {"id": "C05-confinement", "pass": base.validate_confinement(self.rpc_events, self.workspace).passed},
            {"id": "C05-raw-session", "pass": bool(self.raw_incoming) and bool(self.session_events)},
        ]
        return assertions

    def _build_result(self, assertions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        passed = {item["id"]: item.get("pass") is True for item in assertions}
        return {"schema_version": "c05-run-result-v1", "run_id": self.run_id, "arm": self.spec["arm"], "repetition": self.spec.get("repetition"), "fixture_id": self.fixture["id"], "fixture_kind": self.fixture["kind"], "pass": all(passed.values()), "assertions": list(assertions), "failed_assertions": [item["id"] for item in assertions if item.get("pass") is not True], "exception": self.exception_info, "identity_valid": passed.get("C05-identity", False), "raw_valid": passed.get("C05-raw-session", False), "process_valid": passed.get("C05-process", False), "prompts_delivered": sum(item.get("type") == "prompt" for item in self.outgoing_commands), "guard_fired": guard_fired(self.consortium_events, self.fixture["prompts"][1]), "continuity": passed.get("C05-continuity", False), "control_regression": not passed.get("C05-control", False), "wall_clock_ms": round(self.wall_clock_ms, 1), "tool_calls": sum(event.get("type") == "tool_execution_start" for event in self.rpc_events)}

    def _safe_validate_all(self) -> list[dict[str, Any]]:
        try:
            return self._validate_all()
        except Exception as exc:
            return [{"id": "C05-protocol", "pass": False, "details": f"validation exception: {type(exc).__name__}: {exc}"}]

    def run(self) -> dict[str, Any]:
        """Run once; preflight precedes all materialization and harvest failures are mandatory."""
        preflight = self.preflight(all_targets=False)
        if not preflight["pass"]:
            assertions = [{"id": "C05-preflight", "pass": False}]
            return self._build_result(assertions) | {"exception": preflight.get("exception")}
        self.harvest_allowed = True
        try:
            self._materialize_workspace()
            stderr_path, rpc_log_path = self.runtime_root / "rpc-stderr.log", self.runtime_root / "rpc-events.jsonl"
            start = time.monotonic()
            proc = self._spawn_pi(self.manifest["argv"], stderr_path)
            try:
                self._run_rpc_loop(proc, rpc_log_path, stderr_path)
            finally:
                self._cleanup_process(proc)
                self.wall_clock_ms = (time.monotonic() - start) * 1000
            self._collect_consortium_logs()
            self._collect_session_logs()
            result = self._build_result(self._safe_validate_all())
        except Exception as exc:
            self.exception_info = f"{type(exc).__name__}: {exc}"
            self.protocol_errors.append(self.exception_info)
            result = self._build_result(self._safe_validate_all()) | {"exception": self.exception_info}
        try:
            self._harvest(result)
            result["raw_valid"] = self._raw_valid()
            result["assertions"] = [item if item["id"] != "C05-raw-session" else {"id": "C05-raw-session", "pass": result["raw_valid"]} for item in result["assertions"]]
            result["failed_assertions"] = [item["id"] for item in result["assertions"] if item.get("pass") is not True]
            result["pass"] = not result["failed_assertions"]
            result["exit_class"] = exit_class(result["assertions"])
            (self.evidence_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            self._refresh_evidence_manifest()
            if not self._raw_valid():
                result["raw_valid"] = False
                result["assertions"] = [item if item["id"] != "C05-raw-session" else {"id": "C05-raw-session", "pass": False} for item in result["assertions"]] + [{"id": "C05-harvest", "pass": False, "details": "final result/manifest mismatch"}]
                result["failed_assertions"] = [item["id"] for item in result["assertions"] if item.get("pass") is not True]
                result["pass"] = False
                result["exit_class"] = 2
                (self.evidence_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                self._refresh_evidence_manifest()
            elif self.frozen.get("consume_ledger"):
                try:
                    ledger_sha, _ = consume_ledger_record(Path(self.frozen.get("ledger_path", LEDGER_PATH)), self.frozen["ledger_sha256"], self.run_id, self.evidence_dir / "result.json", result["exit_class"])
                    result["ledger_sha256"] = ledger_sha
                except Exception as exc:
                    result["pass"] = False
                    result["ledger_error"] = f"Ledger consumption failed: {type(exc).__name__}: {exc}"
                    result["exit_class"] = 2
        except Exception as exc:
            result["pass"] = False
            result["harvest_error"] = f"Harvest failed: {exc}"
            result["assertions"].append({"id": "C05-harvest", "pass": False})
            result["exit_class"] = 2
            return result
        return result

    def _raw_valid(self) -> bool:
        manifest_path = self.evidence_dir / "evidence-manifest.json"
        required = {"manifest.json", "result.json", "raw-incoming.jsonl", "outgoing-commands.jsonl", "combined-directional.jsonl", "rpc-stderr.log", "state_final.json", "entries_final.json", "stats_final.json", "text_final.json", f"fixture-before/{self.fixture['target']}", f"fixture-after/{self.fixture['target']}"}
        sessions = list((self.evidence_dir / "sessions").rglob("*.jsonl")) if (self.evidence_dir / "sessions").is_dir() else []
        consortium = list((self.evidence_dir / "consortium").rglob("*.jsonl")) if (self.evidence_dir / "consortium").is_dir() else []
        if not manifest_path.is_file() or not sessions or not consortium:
            return False
        data = json.loads(manifest_path.read_text())
        files = {item.get("path"): item for item in data.get("files", [])}
        return required.issubset(files) and all((self.evidence_dir / rel).is_file() and sha256_file(self.evidence_dir / rel) == item.get("sha256") for rel, item in files.items())

    def _refresh_evidence_manifest(self) -> None:
        files = [
            {"path": str(path.relative_to(self.evidence_dir)), "sha256": sha256_file(path), "size": path.stat().st_size}
            for path in sorted(self.evidence_dir.rglob("*"))
            if path.is_file() and path.name != "evidence-manifest.json"
        ]
        (self.evidence_dir / "evidence-manifest.json").write_text(json.dumps({"run_id": self.run_id, "files": files, "coverage": {"total_files": len(files), "total_bytes": sum(item["size"] for item in files)}}, indent=2) + "\n")

    def _harvest(self, result: Mapping[str, Any]) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, default=str) + "\n")
        for source, name in ((getattr(self, "fixture_before", None), "fixture-before"), (self.workspace, "fixture-after")):
            destination = self.evidence_dir / name
            destination.mkdir()
            if source and source.exists():
                for file in source.rglob("*"):
                    if file.is_file():
                        target = destination / file.relative_to(source)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, target)
        for name in ("live-boundary.json", "rpc-events.jsonl"):
            source = self.runtime_root / name
            if source.exists():
                shutil.copy2(source, self.evidence_dir / name)
        (self.evidence_dir / "raw-incoming.jsonl").write_text("\n".join(self.raw_incoming) + ("\n" if self.raw_incoming else ""))
        (self.evidence_dir / "outgoing-commands.jsonl").write_text("\n".join(json.dumps(item) for item in self.outgoing_records) + ("\n" if self.outgoing_records else ""))
        (self.evidence_dir / "combined-directional.jsonl").write_text("\n".join(json.dumps(item) for item in self.directional_records) + ("\n" if self.directional_records else ""))
        (self.evidence_dir / "rpc-stderr.log").write_text("\n".join(self.stderr_lines) + ("\n" if self.stderr_lines else ""))
        for source, name in ((self.sessions_dir, "sessions"), (self.workspace / ".pi" / "consortium", "consortium")):
            destination = self.evidence_dir / name
            destination.mkdir()
            if source.exists():
                for file in source.rglob("*"):
                    if file.is_file():
                        target = destination / file.relative_to(source)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, target)
        for key in ("state_final", "entries_final", "stats_final", "text_final"):
            if key in self.responses:
                (self.evidence_dir / f"{key}.json").write_text(json.dumps(self.responses[key], indent=2, default=str) + "\n")
        (self.evidence_dir / "result.json").write_text(json.dumps(dict(result), indent=2, default=str) + "\n")
        self._refresh_evidence_manifest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="c05 prospective runner")
    parser.add_argument("--run-id", choices=sorted(BY_ID)); parser.add_argument("--freeze-commit")
    for name in ("phase0", "contract", "review", "ledger"): parser.add_argument(f"--{name}-sha256")
    parser.add_argument("--smoke-decision-path")
    parser.add_argument("--smoke-decision-sha256")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--consume-ledger", action="store_true")
    parser.add_argument("--build-smoke-decision", type=Path)
    args = parser.parse_args(argv)
    if args.build_smoke_decision:
        if args.preflight_only or args.consume_ledger:
            parser.error("--build-smoke-decision is a separate mode")
        decision = build_smoke_decision(LEDGER_PATH, args.build_smoke_decision)
        print(json.dumps(decision, indent=2)); return 0
    required = ("run_id", "freeze_commit", "phase0_sha256", "contract_sha256", "review_sha256", "ledger_sha256")
    if any(getattr(args, name) is None for name in required):
        parser.error("live/preflight cells require --run-id, --freeze-commit, and all SHA256 values")
    if args.preflight_only and args.consume_ledger:
        parser.error("--consume-ledger is forbidden with --preflight-only")
    if not args.preflight_only and not args.consume_ledger:
        parser.error("live cells require --consume-ledger")
    if not BY_ID[args.run_id]["smoke"] and (not args.smoke_decision_path or not args.smoke_decision_sha256):
        parser.error("matrix runs require --smoke-decision-path and --smoke-decision-sha256")
    runner = C05Runner(BY_ID[args.run_id], **vars(args))
    result = runner.preflight(all_targets=True) if args.preflight_only else runner.run()
    print(json.dumps(result, indent=2)); return 0 if result.get("pass") else result.get("exit_class", 2)

if __name__ == "__main__": raise SystemExit(main())
