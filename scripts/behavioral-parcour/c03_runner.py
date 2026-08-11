#!/usr/bin/env python3
"""Fresh c03 supersession-guard runner with explicit end-to-end model identity."""
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
import phase05_runner as p

REPO_ROOT = p.REPO_ROOT
CORPUS_PATH = HERE / "c03-supersession-corpus.json"
CONTRACT_PATH = HERE / "c03-contract-files.json"
REVIEW_SESSION_PATH = REPO_ROOT / "docs" / "c03-evidence" / "independent-review-8081-twins-session.jsonl"
LEDGER_PATH = REPO_ROOT / "docs" / "c03-evidence" / "raw-publication-ledger.json"
PI_VERSION = "0.84.1"
NODE_VERSION_PATTERN = re.compile(r"v22\.23\.\d+\Z")
MODEL_PROVIDER = "8081-twins"
MODEL_ID = "qwen36-27b-nvidia-nvfp4"
MODEL_REF = f"{MODEL_PROVIDER}/{MODEL_ID}"
THINKING_LEVEL = "off"
GUARD_REASON = "Explicit durable-state supersession guard"


def sha256_file(path: Path) -> str:
    return p.sha256_file(path)


def load_corpus() -> Dict[str, Dict[str, Any]]:
    data = json.loads(CORPUS_PATH.read_text())
    if data.get("schema_version") != "c03-supersession-corpus-v1":
        raise ValueError("unsupported c03 corpus schema")
    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 8:
        raise ValueError("c03 corpus must contain exactly eight fixtures")
    mapped = {item.get("id"): item for item in fixtures if isinstance(item, dict) and isinstance(item.get("id"), str)}
    if len(mapped) != 8:
        raise ValueError("c03 corpus fixture IDs must be unique")
    if sum(item.get("kind") == "positive" for item in mapped.values()) != 4 or sum(item.get("kind") == "control" for item in mapped.values()) != 4:
        raise ValueError("c03 corpus must contain four positive and four control fixtures")
    for item in mapped.values():
        target = item.get("target")
        if not isinstance(target, str) or Path(target).is_absolute() or ".." in Path(target).parts:
            raise ValueError("c03 fixture target is invalid")
        if not isinstance(item.get("before"), str) or not isinstance(item.get("prompts"), list) or len(item["prompts"]) != 3:
            raise ValueError("c03 fixture must provide before text and exactly three prompts")
    return mapped


FIXTURES = load_corpus()
FIXTURE_ORDER = list(FIXTURES)
RUN_SPECS = [
    {"run_id": f"c03-{arm}-r{repetition}-{fixture_id}", "arm": arm, "repetition": repetition, "fixture_id": fixture_id}
    for repetition in (1, 2, 3)
    for fixture_id in FIXTURE_ORDER
    for arm in ("off", "on")
]
RUN_BY_ID = {item["run_id"]: item for item in RUN_SPECS}


def run_target_paths(specs: List[Dict[str, Any]]) -> List[Path]:
    return [path for spec in specs for path in (Path("/tmp") / f"parcour-{spec['run_id']}", REPO_ROOT / ".parcour-runs" / spec["run_id"])]


def arm_guard_enabled(spec: Dict[str, Any]) -> bool:
    arm = spec.get("arm")
    if arm not in ("off", "on"):
        raise ValueError("c03 arm must be off or on")
    return arm == "on"


def build_child_env(ambient: Dict[str, str]) -> Dict[str, str]:
    return {**ambient, "PI_SKIP_VERSION_CHECK": "1", "CONSORTIUM_MODEL": MODEL_REF}


def build_pi_command(workspace: Path, sessions: Path, run_id: str) -> List[str]:
    return [
        "pi", "--mode", "rpc", "--no-context-files", "--no-skills", "--no-prompt-templates",
        "--no-extensions", "--tools", "read,edit,grep,find,ls",
        "-e", str(p.PROVIDER_EXT), "-e", str(p.CONSORTIUM_EXT), "-e", str(p.FOCUS_EXT),
        "--provider", MODEL_PROVIDER, "--model", MODEL_ID, "--thinking", THINKING_LEVEL,
        "--dm-off", "--write-guard", str(workspace), "--approve",
        "--session-dir", str(sessions), "--name", run_id,
    ]


def guard_fired(events: List[Dict[str, Any]]) -> bool:
    return any(
        event.get("type") in ("injection_complete", "injection_skipped")
        and event.get("governor_reason") == GUARD_REASON
        for event in events
    )


def continuity_passes(fixture: Dict[str, Any], final_text: str) -> bool:
    if fixture.get("kind") != "positive":
        return True
    lower = final_text.lower()
    current = all(marker.lower() in lower for marker in fixture.get("current_markers", []))
    historical = True
    for marker in fixture.get("historical_markers", []):
        needle = marker.lower()
        position = lower.find(needle)
        if position < 0:
            historical = False
            continue
        context = lower[max(0, position - 100): position + len(needle) + 100]
        if not any(word in context for word in ("supersed", "histor", "replac", "former", "previous", "retired", "migrated")):
            historical = False
    return current and historical


def review_timing_is_valid(freeze_timestamp: str, review_timestamp: str, preflight_timestamp: str) -> bool:
    try:
        parse = lambda value: datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        freeze, review, preflight = parse(freeze_timestamp), parse(review_timestamp), parse(preflight_timestamp)
        return freeze < review <= preflight
    except (TypeError, ValueError):
        return False


def verify_review_session(expected_sha256: str) -> Dict[str, Any]:
    if not REVIEW_SESSION_PATH.is_file() or sha256_file(REVIEW_SESSION_PATH) != expected_sha256:
        raise RuntimeError("c03 review session evidence mismatch")
    events = [json.loads(line) for line in REVIEW_SESSION_PATH.read_text().splitlines() if line.strip()]
    model = next((event for event in events if event.get("type") == "model_change"), None)
    thinking = next((event for event in events if event.get("type") == "thinking_level_change"), None)
    info = next((event for event in events if event.get("type") == "session_info"), None)
    messages = [event for event in events if event.get("type") == "message" and event.get("message", {}).get("role") == "assistant"]
    final_text = "" if not messages else "".join(item.get("text", "") for item in messages[-1]["message"].get("content", []) if isinstance(item, dict))
    checks = {
        "session_name": isinstance(info, dict) and str(info.get("name", "")).startswith("c03-8081-twins"),
        "provider": isinstance(model, dict) and model.get("provider") == MODEL_PROVIDER,
        "model": isinstance(model, dict) and model.get("modelId") == MODEL_ID,
        "thinking": isinstance(thinking, dict) and thinking.get("thinkingLevel") == THINKING_LEVEL,
        "pass_verdict": re.search(r"(?:HEADLINE[^\n]*PASS|\*\*PASS\*\*)", final_text, re.IGNORECASE) is not None,
        "no_blocker": re.search(r"BLOCKER\s*:\s*(?:None|No\b)", final_text, re.IGNORECASE) is not None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"c03 review session gate failed: {checks}")
    return {"checks": checks, "session_timestamp": events[0].get("timestamp"), "event_count": len(events)}


def verify_publication_ledger(require_all_unconsumed: bool) -> Dict[str, Any]:
    if not LEDGER_PATH.is_file():
        raise RuntimeError("c03 raw-publication ledger is missing")
    data = json.loads(LEDGER_PATH.read_text())
    if data.get("schema_version") != "c03-raw-publication-ledger-v1" or not isinstance(data.get("runs"), list):
        raise RuntimeError("c03 raw-publication ledger schema invalid")
    expected_ids = [spec["run_id"] for spec in RUN_SPECS]
    records = data["runs"]
    if [record.get("run_id") for record in records] != expected_ids:
        raise RuntimeError("c03 raw-publication ledger order/IDs mismatch")
    for record in records:
        run_id = record["run_id"]
        expected_dir = f"docs/c03-raw/{run_id}"
        if record.get("raw_directory") != expected_dir or not (REPO_ROOT / expected_dir).is_dir():
            raise RuntimeError(f"c03 raw destination mismatch: {run_id}")
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", f"{expected_dir}/.gitkeep"], cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if tracked.returncode != 0:
            raise RuntimeError(f"c03 raw destination not tracked: {run_id}")
        if require_all_unconsumed and record.get("status") != "unconsumed":
            raise RuntimeError(f"c03 run is already consumed before prompt 1: {run_id}")
    return data


def verify_contract(expected_sha256: str, freeze_commit: str) -> Dict[str, Any]:
    if sha256_file(CONTRACT_PATH) != expected_sha256:
        raise RuntimeError("c03 contract SHA-256 mismatch")
    data = json.loads(CONTRACT_PATH.read_text())
    if data.get("schema_version") != "c03-contract-files-v1" or not isinstance(data.get("files"), list):
        raise RuntimeError("c03 contract schema invalid")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", freeze_commit, "HEAD"], cwd=REPO_ROOT, check=False)
    if ancestor.returncode != 0:
        raise RuntimeError("c03 freeze commit is not an ancestor of HEAD")
    paths: set[str] = set()
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise RuntimeError("c03 contract entry invalid")
        rel, expected = item["path"], item["sha256"]
        if not isinstance(rel, str) or rel in paths or rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError("c03 contract path invalid")
        paths.add(rel)
        target = REPO_ROOT / rel
        if not target.is_file() or sha256_file(target) != expected:
            raise RuntimeError(f"c03 current contract file mismatch: {rel}")
        frozen = subprocess.run(["git", "show", f"{freeze_commit}:{rel}"], cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if frozen.returncode != 0 or p.sha256_bytes(frozen.stdout) != expected:
            raise RuntimeError(f"c03 frozen contract file mismatch: {rel}")
    if not paths:
        raise RuntimeError("c03 contract has no files")
    return data


class C03Sequencer:
    def __init__(self, prompts: List[str]) -> None:
        self.prompts = prompts
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
                        {"id": "state_final", "type": "get_state"}, {"id": "entries_final", "type": "get_entries"},
                        {"id": "stats_final", "type": "get_session_stats"}, {"id": "text_final", "type": "get_last_assistant_text"},
                    ])
                    self.final_queries = True
        required = {"state_final", "entries_final", "stats_final", "text_final"}
        if self.final_queries and required.issubset(self.responses):
            self.complete = True
        return actions


class C03Runner(p.Phase05Runner):
    def __init__(self, spec: Dict[str, Any], freeze_commit: str, runner_sha256: str, corpus_sha256: str, contract_sha256: str, review_session_sha256: str) -> None:
        super().__init__(spec["run_id"], spec["repetition"], "0" * 40, "0" * 40, "0" * 64, freeze_commit)
        self.spec = spec
        self.fixture = FIXTURES[spec["fixture_id"]]
        self.freeze_commit = freeze_commit
        self.expected_runner_sha = runner_sha256
        self.corpus_sha256 = corpus_sha256
        self.expected_contract_sha = contract_sha256
        self.review_session_sha256 = review_session_sha256
        self.tmp_root = Path("/tmp") / f"parcour-{self.run_id}"
        self.workspace = self.tmp_root / "workspace"
        self.sessions_dir = self.tmp_root / "sessions"
        self.runtime_root = self.tmp_root
        self.evidence_dir = REPO_ROOT / ".parcour-runs" / self.run_id
        self.fixture_before: Optional[Path] = None
        self.frozen_checks: Dict[str, bool] = {}

    def _validate_frozen_inputs(self) -> None:
        if self.spec != RUN_BY_ID.get(self.run_id):
            raise RuntimeError("c03 run ID does not match frozen schedule")
        for value, length, label in (
            (self.freeze_commit, 40, "freeze commit"), (self.expected_runner_sha, 64, "runner sha"),
            (self.corpus_sha256, 64, "corpus sha"), (self.expected_contract_sha, 64, "contract sha"),
            (self.review_session_sha256, 64, "review session sha"),
        ):
            if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
                raise RuntimeError(f"invalid {label}")
        contract = verify_contract(self.expected_contract_sha, self.freeze_commit)
        review = verify_review_session(self.review_session_sha256)
        freeze_timestamp = p.cmd_output(["git", "show", "-s", "--format=%cI", self.freeze_commit], cwd=REPO_ROOT)["output"].strip()
        preflight_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        review_timing = review_timing_is_valid(freeze_timestamp, str(review.get("session_timestamp", "")), preflight_timestamp)
        if sha256_file(Path(__file__).resolve()) != self.expected_runner_sha:
            raise RuntimeError("c03 runner SHA mismatch")
        if sha256_file(CORPUS_PATH) != self.corpus_sha256:
            raise RuntimeError("c03 corpus SHA mismatch")
        pi = p.cmd_output(["pi", "--version"])
        node = p.cmd_output(["node", "--version"])
        command = build_pi_command(self.workspace, self.sessions_dir, self.run_id)
        child_env = build_child_env(dict(os.environ))
        self.frozen_checks = {
            "contract_nonempty": bool(contract.get("files")),
            "review_identity_and_verdict": all(review["checks"].values()),
            "review_after_freeze_before_preflight": review_timing,
            "pi_version": pi["exit_code"] == 0 and pi["output"].strip() == PI_VERSION,
            "node_version": node["exit_code"] == 0 and NODE_VERSION_PATTERN.fullmatch(node["output"].strip()) is not None,
            "executor_provider": command[command.index("--provider") + 1] == MODEL_PROVIDER,
            "executor_model": command[command.index("--model") + 1] == MODEL_ID,
            "executor_thinking": command[command.index("--thinking") + 1] == THINKING_LEVEL,
            "effective_consortium_model": child_env.get("CONSORTIUM_MODEL") == MODEL_REF,
            "extension_order": [command[index + 1] for index, value in enumerate(command) if value == "-e"] == [str(p.PROVIDER_EXT), str(p.CONSORTIUM_EXT), str(p.FOCUS_EXT)],
        }
        failed = [key for key, value in self.frozen_checks.items() if value is not True]
        if failed:
            raise RuntimeError(f"c03 frozen identity checks failed: {failed}")

    def _guard_existing_paths(self, all_targets: bool) -> None:
        specs = RUN_SPECS if all_targets else [self.spec]
        conflicts = [str(path) for path in run_target_paths(specs) if path.exists()]
        if conflicts:
            raise FileExistsError(f"refusing existing c03 targets: {conflicts}")

    def _build_manifest(self) -> Dict[str, Any]:
        command = build_pi_command(self.workspace, self.sessions_dir, self.run_id)
        pi = p.cmd_output(["pi", "--version"])
        node = p.cmd_output(["node", "--version"])
        self.manifest = {
            "schema_version": "c03-run-manifest-v1", "run_id": self.run_id, "arm": self.spec["arm"],
            "repetition": self.spec["repetition"], "fixture_id": self.fixture["id"], "fixture_kind": self.fixture["kind"],
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "workspace": str(self.workspace),
            "runtime_root": str(self.runtime_root), "argv": command,
            "expected": {"freeze_commit": self.freeze_commit, "runner_sha256": self.expected_runner_sha, "corpus_sha256": self.corpus_sha256, "contract_sha256": self.expected_contract_sha, "review_session_sha256": self.review_session_sha256},
            "runtime_versions": {"pi_cli": pi, "node_cli": node},
            "child_environment": {"CONSORTIUM_MODEL": build_child_env(dict(os.environ))["CONSORTIUM_MODEL"], "PI_SKIP_VERSION_CHECK": "1"},
            "identity_checks": copy.deepcopy(self.frozen_checks),
        }
        return self.manifest

    def _preflight(self, all_targets: bool) -> None:
        self._validate_frozen_inputs()
        ledger = verify_publication_ledger(require_all_unconsumed=all_targets)
        self.frozen_checks["publication_ledger"] = len(ledger["runs"]) == 48
        self._guard_existing_paths(all_targets)
        self._build_manifest()

    def preflight(self) -> Dict[str, Any]:
        try:
            self._preflight(all_targets=True)
            return {"schema_version": "c03-preflight-v1", "run_id": self.run_id, "pass": True, "prompts_delivered": 0, "manifest": self.manifest}
        except Exception as exc:
            return {"schema_version": "c03-preflight-v1", "run_id": self.run_id, "pass": False, "prompts_delivered": 0, "exception": f"{type(exc).__name__}: {exc}", "manifest": self.manifest}

    def _materialize_workspace(self) -> None:
        self.tmp_root.mkdir(parents=True)
        self.workspace.mkdir()
        self.sessions_dir.mkdir()
        target = self.workspace / self.fixture["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.fixture["before"])
        settings = self.workspace / ".pi" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        enabled = arm_guard_enabled(self.spec)
        settings.write_text(json.dumps({"consortium": {"enabled": True, "governorMode": "smart_extractor", "stateSupersessionGuard": enabled}}, indent=2) + "\n")
        persisted = json.loads(settings.read_text()).get("consortium", {}).get("stateSupersessionGuard")
        self.manifest["workspace_guard_setting"] = persisted
        self.manifest["identity_checks"]["workspace_guard_setting"] = persisted is enabled
        if persisted is not enabled:
            raise RuntimeError("c03 workspace guard setting mismatch before Pi launch")
        self.fixture_before = self.tmp_root / "fixture-before"
        before_target = self.fixture_before / self.fixture["target"]
        before_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, before_target)

    def _spawn_pi(self, command: List[str], stderr_path: Path) -> subprocess.Popen:
        stderr_handle = stderr_path.open("wb")
        proc = subprocess.Popen(
            command, cwd=str(self.workspace), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_handle,
            env=build_child_env(dict(os.environ)), start_new_session=True,
        )
        proc._stderr_handle = stderr_handle  # type: ignore[attr-defined]
        return proc

    def _run_rpc_loop(self, proc: subprocess.Popen, rpc_log_path: Path, stderr_path: Path) -> None:
        assert proc.stdin is not None and proc.stdout is not None
        buffer = b""
        total_start = time.monotonic()
        turn_start: Optional[float] = None
        sequencer = C03Sequencer(self.fixture["prompts"])
        reported_errors = 0
        self._send(proc, {"id": "get_state", "type": "get_state"})
        self._send(proc, {"id": "get_commands", "type": "get_commands"})
        with rpc_log_path.open("wb") as rpc_log:
            while not sequencer.complete:
                if time.monotonic() - total_start > p.TIMEOUT_SECONDS * 3:
                    self.timeout_occurred = True; self.protocol_errors.append("Total timeout"); self._terminate_process_group(proc); break
                if turn_start is not None and time.monotonic() - turn_start > p.TIMEOUT_SECONDS:
                    self.timeout_occurred = True; self.protocol_errors.append("Per-turn timeout"); self._terminate_process_group(proc); break
                ready, _, _ = select.select([proc.stdout], [], [], 1.0)
                if not ready:
                    if proc.poll() is not None: break
                    continue
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk: break
                rpc_log.write(chunk); rpc_log.flush(); buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    raw = raw[:-1] if raw.endswith(b"\r") else raw
                    if not raw: continue
                    text = raw.decode("utf-8", errors="replace"); self.raw_incoming.append(text)
                    try: event = json.loads(text)
                    except json.JSONDecodeError as exc: self.protocol_errors.append(f"Invalid JSON: {exc}"); continue
                    self.rpc_events.append(event); self._record_direction("out", event)
                    if event.get("type") == "response" and event.get("id"): self.responses[str(event["id"])] = event
                    actions = sequencer.on_event(event)
                    if len(sequencer.errors) > reported_errors:
                        self.protocol_errors.extend(sequencer.errors[reported_errors:]); reported_errors = len(sequencer.errors)
                    if sequencer.errors: break
                    if event.get("type") == "agent_settled": turn_start = None
                    for action in actions:
                        if action.get("type") == "prompt":
                            if action.get("id") == "prompt_0" and self.live_boundary_ts is None:
                                self.live_boundary_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
                                (self.tmp_root / "live-boundary.json").write_text(json.dumps({"run_id": self.run_id, "ts": self.live_boundary_ts}, indent=2) + "\n")
                            turn_start = time.monotonic()
                        self._send(proc, action)
                if sequencer.errors: break
        if buffer.strip(): self.protocol_errors.append("Unterminated stdout bytes")
        if not sequencer.complete and not self.timeout_occurred and not sequencer.errors: self.protocol_errors.append("RPC stream ended before final responses")
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
        assertions: List[p.Assertion] = []
        def add(identifier: str, passed: bool, details: str) -> None:
            item = p.Assertion(identifier, details); item.passed = passed; item.details = details; item.evidence = [{"file": "result.json", "assertion": identifier}]; assertions.append(item)
        rc = self.process_returncode if self.process_returncode is not None else -1
        add("C03-process", rc == 0, f"returncode={rc}")
        initial = self.responses.get("get_state", {}).get("data", {})
        final = self.responses.get("state_final", {}).get("data", {})
        add("C03-executor-provider", initial.get("provider") == MODEL_PROVIDER and final.get("provider") == MODEL_PROVIDER, f"initial={initial.get('provider')}; final={final.get('provider')}")
        add("C03-executor-model", initial.get("modelId") == MODEL_ID and final.get("modelId") == MODEL_ID, f"initial={initial.get('modelId')}; final={final.get('modelId')}")
        add("C03-executor-thinking", initial.get("thinkingLevel") == THINKING_LEVEL and final.get("thinkingLevel") == THINKING_LEVEL, f"initial={initial.get('thinkingLevel')}; final={final.get('thinkingLevel')}")
        prompts = [item for item in self.outgoing_commands if item.get("type") == "prompt"]
        add("C03-prompts", [item.get("message") for item in prompts] == self.fixture["prompts"], f"count={len(prompts)}")
        add("C03-protocol", not self.protocol_errors, f"errors={self.protocol_errors}")
        identities = self.manifest.get("identity_checks", {})
        add("C03-preflight-identities", bool(identities) and all(value is True for value in identities.values()), f"checks={identities}")
        starts = [event for event in self.consortium_events if event.get("type") == "deliberation_start"]
        trace_valid = bool(starts) and all(event.get("model") == MODEL_REF and event.get("modelSource") == "CONSORTIUM_MODEL" for event in starts)
        add("C03-trace-identity", trace_valid, f"starts={len(starts)}; models={sorted({str(event.get('model')) for event in starts})}; sources={sorted({str(event.get('modelSource')) for event in starts})}")
        fired = guard_fired(self.consortium_events)
        expected_guard = self.spec["arm"] == "on" and self.fixture["kind"] == "positive"
        add("C03-guard", fired == expected_guard, f"expected={expected_guard}; observed={fired}")
        target = self.workspace / self.fixture["target"]
        text = target.read_text() if target.exists() else ""
        continuity = continuity_passes(self.fixture, text)
        add("C03-continuity", continuity, f"positive={self.fixture['kind'] == 'positive'}; continuity={continuity}")
        return assertions

    def _refresh_evidence_manifest(self) -> None:
        files = [{"path": str(file.relative_to(self.evidence_dir)), "sha256": sha256_file(file), "size": file.stat().st_size} for file in sorted(self.evidence_dir.rglob("*")) if file.is_file() and file.name != "evidence-manifest.json"]
        (self.evidence_dir / "evidence-manifest.json").write_text(json.dumps({"run_id": self.run_id, "files": files, "coverage": {"total_files": len(files), "total_bytes": sum(item["size"] for item in files)}}, indent=2) + "\n")

    def _harvest(self, result: Dict[str, Any]) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, default=str) + "\n")
        for source, target_name in ((self.fixture_before, "fixture-before"), (self.workspace, "fixture-after")):
            target_root = self.evidence_dir / target_name; target_root.mkdir()
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

    def run(self) -> Dict[str, Any]:
        result: Dict[str, Any]
        try:
            self._preflight(all_targets=False); self.harvest_allowed = True; self._materialize_workspace()
            command = build_pi_command(self.workspace, self.sessions_dir, self.run_id)
            stderr = self.tmp_root / "rpc-stderr.log"; rpc_log = self.tmp_root / "rpc-events.jsonl"
            started = time.monotonic(); proc = self._spawn_pi(command, stderr)
            try: self._run_rpc_loop(proc, rpc_log, stderr)
            finally: self._cleanup_process(proc); self.wall_clock_ms = (time.monotonic() - started) * 1000
            self._collect_consortium_logs(); self._collect_session_logs()
            self.manifest.update({"ended_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "wall_clock_ms": round(self.wall_clock_ms, 1), "process_returncode": self.process_returncode, "live_boundary_timestamp": self.live_boundary_ts})
            assertions = self._validate_all()
            result = {"schema_version": "c03-run-result-v1", "run_id": self.run_id, "arm": self.spec["arm"], "repetition": self.spec["repetition"], "fixture_id": self.fixture["id"], "fixture_kind": self.fixture["kind"], "pass": all(item.passed for item in assertions), "process_returncode": self.process_returncode, "wall_clock_ms": round(self.wall_clock_ms, 1), "prompts_delivered": len([item for item in self.outgoing_commands if item.get("type") == "prompt"]), "exception": None, "assertions": [item.to_dict() for item in assertions], "c03": {"guard_fired": guard_fired(self.consortium_events), "continuity_passes": continuity_passes(self.fixture, (self.workspace / self.fixture["target"]).read_text() if (self.workspace / self.fixture["target"]).exists() else ""), "tool_call_count": sum(event.get("type") == "tool_execution_start" for event in self.rpc_events)}, "manifest": self.manifest}
        except Exception as exc:
            self.exception_info = f"{type(exc).__name__}: {exc}"; self.protocol_errors.append(self.exception_info)
            assertions = self._validate_all() if self.workspace.exists() else []
            result = {"schema_version": "c03-run-result-v1", "run_id": self.run_id, "arm": self.spec["arm"], "repetition": self.spec["repetition"], "fixture_id": self.fixture["id"], "fixture_kind": self.fixture["kind"], "pass": False, "process_returncode": self.process_returncode, "wall_clock_ms": round(self.wall_clock_ms, 1), "prompts_delivered": len([item for item in self.outgoing_commands if item.get("type") == "prompt"]), "exception": self.exception_info, "assertions": [item.to_dict() for item in assertions], "manifest": self.manifest}
        if self.harvest_allowed:
            try: self._harvest(result)
            except Exception as exc: result["pass"] = False; result["harvest_error"] = f"{type(exc).__name__}: {exc}"
        return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="c03 fresh supersession guard runner")
    parser.add_argument("--run-id", required=True, choices=sorted(RUN_BY_ID))
    parser.add_argument("--freeze-commit", required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--review-session-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    runner = C03Runner(RUN_BY_ID[args.run_id], args.freeze_commit, args.runner_sha256, args.corpus_sha256, args.contract_sha256, args.review_session_sha256)
    result = runner.preflight() if args.preflight_only else runner.run()
    print(json.dumps(result, indent=2, default=str))
    if result.get("pass") is True: return 0
    identity_ids = {"C03-process", "C03-executor-provider", "C03-executor-model", "C03-executor-thinking", "C03-prompts", "C03-protocol", "C03-preflight-identities", "C03-trace-identity"}
    if result.get("exception") or result.get("harvest_error") or any(not item.get("pass") and item.get("id") in identity_ids for item in result.get("assertions", [])): return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
