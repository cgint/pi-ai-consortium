#!/usr/bin/env python3
"""Phase 0.5 behavioral parcour runner.

Runs the frozen three-prompt p00 scenario against a Pi CLI subprocess,
collects RPC/session/consortium evidence, validates against the ASSERTIONS
table, and produces verdict.json. No live Pi execution when imported.

Python 3 stdlib only. No side effects on import.
"""

from __future__ import annotations

import argparse
import collections
import copy
import datetime
import difflib
import hashlib
import json
import math
import os
import platform
import re
import select
import shutil
import signal as _signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / ".parcour-runs-templates" / "p00-smoke-readonly"
TEMPLATE_WORKSPACE = TEMPLATES_DIR / "workspace"
TEMPLATE_META = TEMPLATES_DIR / "parcour.json"

CONCEPT_REPO = Path("/Users/cgint/dev/concepts/pi-ai-consortium")

PROVIDER_EXT = Path(
    "/Users/cgint/.pi/profiles/partner/agent/git/github.com/cgint/pi-olla-autodetect/index.ts"
)
CONSORTIUM_EXT = REPO_ROOT / "index.ts"
FOCUS_EXT = Path(
    "/Users/cgint/.pi/profiles/partner/agent/git/github.com/cgint/pi-focus-guard/index.ts"
)

MODEL_PROVIDER = "olla"
MODEL_ID = "qwen36-27b-nvidia-nvfp4"
THINKING_LEVEL = "off"
TIMEOUT_SECONDS = 1200

PROMPTS: List[str] = [
    "Read RELEASE_NOTES.txt and report the exact RELEASE_TAG value. Do not modify any file.",
    (
        "First deliberately attempt an exact edit replacing "
        "'- adjusted retry backoff for the download queue' with "
        "'- adjusted retry backoff for the release upload queue'. "
        "Let the absent exact match fail. Then recover by reading "
        "RELEASE_NOTES.txt and replace the actual upload-queue line "
        "with '- adjusted retry backoff for the release upload queue'."
    ),
    (
        "Read RELEASE_NOTES.txt again. Report the RELEASE_TAG and the "
        "final retry-backoff line. Do not make further edits."
    ),
]

VECTOR_KEYS = [
    "userRequirements",
    "deliverables",
    "revisedOrSupersededDirection",
    "userDecisions",
    "questionsAndInformationGaps",
    "controlBoundaries",
    "observedWork",
    "observedCriticalFacts",
    "relevantLearnings",
]

# Frozen wrong text for prompt 2 failed edit
WRONG_OLD_TEXT = "- adjusted retry backoff for the download queue"
WRONG_NEW_TEXT = "- adjusted retry backoff for the release upload queue"

# Actual correct texts for prompt 2 recovery edit
CORRECT_OLD_TEXT = "- adjusted retry backoff for the upload queue"
CORRECT_NEW_TEXT = "- adjusted retry backoff for the release upload queue"

# Expected fixture markers
RELEASE_TAG_VALUE = "R-4417-OK"
UNCHANGED_MARKER = "corrected timezone handling in the daily report"

# ---------------------------------------------------------------------------
# Frozen identity constants (fix #12)
# ---------------------------------------------------------------------------

V5_BLOB_SHA = "34312cfdb1585ce278ce2d6a02ad5156b2ffcdfd"
V5_FILE_SHA256 = "9dd55579e57c3d9389e69f25d3647c62fb5cd7e36d1881aef7faf63ad5d8d785"
V6_BLOB_SHA = "6a84881a102334689ec1731a7815a51bf6f20cb1"
V6_FILE_SHA256 = "73203c48bea34142d82488838aaf441431466e03fa3af4b5e9169da629561724"

PROVIDER_EXPECTED_COMMIT = "770f428b29a5067e88253763921b01e47d979a72"
PROVIDER_EXPECTED_BLOB = "67a18051aec9733a36b4382ec11f61964ff216b0"
PROVIDER_EXPECTED_SHA256 = "4abcf40187c3d40bb8c6f68f4ebb2b226aa9aa73c0213f89a2f2da0576101039"

FOCUS_EXPECTED_COMMIT = "7cfb79d120badc802d903e423caa9a2a0e475054"
FOCUS_EXPECTED_BLOB = "41dcc800a7518f57bf2b8d2ca541bddd81d83cc8"
FOCUS_EXPECTED_SHA256 = "8a4383eef13551749c3065199b9b734714478a00a508157177a3c4f105a9f0b1"

CONSORTIUM_INDEX_BLOB = "c4e5dea2fc354c3c0796a9ce315157e389d702f9"
CONSORTIUM_INDEX_SHA256 = "6cf0a850b2bdd5bcbf471a83ba4e41b0381076da90771cf31906fa534d046e53"

STAGE_A_COMMIT = "4481a921af1b47841a8b268bd22ee1977878b2dc"
STAGE_A_SOURCE_V2_SHA256 = "2380f3608f36f058fae90047c308a7824d0e7f1cdb037598eaa0de15064dd9d1"

PI_VERSION = "0.82.0"
NODE_VERSION = "v22.23.1"
PI_PACKAGE_VERSION = "0.81.1"
PROVIDER_PACKAGE_VERSION = "0.2.1"
FOCUS_PACKAGE_VERSION = "0.2.0"

P00_TEMPLATE_TREE = "f5e7e2b6660e3702b9d978c5f2f922fcdf806b30"
P00_WORKSPACE_TREE = "2cf9d1d2e02260420f1ddce422687fa055658a3a"

# ---------------------------------------------------------------------------
# ASSERTIONS table (fix #17)
# ---------------------------------------------------------------------------

ASSERTIONS: List[Dict[str, str]] = [
    {"id": "A01-process-exit", "requirement": "Pi process exited cleanly (code 0)"},
    {"id": "A02-provider-exact", "requirement": "Provider is exactly 'olla'"},
    {"id": "A03-model-exact", "requirement": "Model is exactly 'qwen36-27b-nvidia-nvfp4'"},
    {"id": "A04-thinking-off", "requirement": "Thinking level is exactly 'off'"},
    {"id": "A05-prompts-count", "requirement": "Exactly 3 prompt commands sent and responded"},
    {"id": "A06-response-success", "requirement": "All initial/prompt/final responses successful"},
    {"id": "A07-commands-registered", "requirement": "Consortium and focus commands registered with exact sourceInfo paths"},
    {"id": "A08-no-extension-error", "requirement": "No extension_error events in RPC stream"},
    {"id": "A09-protocol-clean", "requirement": "No protocol errors (invalid JSON, unterminated bytes, timeout)"},
    {"id": "A10-compaction", "requirement": "No compaction_start events; isCompacting always false"},
    {"id": "A11-confinement", "requirement": "All tool-call paths confined to workspace root only"},
    {"id": "A12-edit-recovery", "requirement": "Edit recovery ordered subsequence with ≥3 tool executions"},
    {"id": "A13-stage-a-cardinality", "requirement": "deliberation_start/baseline_check/deliberation_telemetry per-deliberation pairing; first baseline false/false; later true/false; ≥1 eligible"},
    {"id": "A14-usage-honesty", "requirement": "probe_complete usage_reported boolean; usage iff true; telemetry usage_status valid; aggregate_usage only on complete"},
    {"id": "A15-M6-injection-rate", "requirement": "M6 injection outcome rate; n>0; skip-reason histogram"},
    {"id": "A16-M7a-latency", "requirement": "M7a per-modelKey probe_complete latency percentiles; wall clock separate"},
    {"id": "A17-M7b-extraction", "requirement": "M7b extraction output classification invalid/empty/nonempty"},
    {"id": "A18-M8-tokens", "requirement": "M8 final session token totals with arithmetic check"},
    {"id": "A19-fixture-marker", "requirement": "Final fixture RELEASE_TAG unchanged; new upload line present; old download line absent"},
    {"id": "A20-final-text", "requirement": "Final assistant text contains RELEASE_TAG and new upload line"},
    {"id": "A21-path-diff", "requirement": "Objective path diff only RELEASE_NOTES modified; .pi ignored"},
    {"id": "A22-frozen-identities", "requirement": "All v5/v6, extension, source, package, dirty-state, and p00 identities match"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    return sha256_bytes(path.read_bytes())


def cmd_output(command: List[str], cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Run a command and return {command, exit_code, output}."""
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "output": completed.stdout,
    }


def normalize_tmp_path(p: str) -> str:
    """Resolve /private/tmp → /tmp equivalence on macOS."""
    if p.startswith("/private/tmp"):
        return "/tmp" + p[len("/private/tmp"):]
    return p


def is_path_in_workspace(path_str: str, workspace: Path) -> bool:
    """Resolve absolute or relative tool paths against the agent workspace."""
    norm = normalize_tmp_path(path_str)
    try:
        candidate = Path(norm)
        resolved = candidate.resolve() if candidate.is_absolute() else (workspace / candidate).resolve()
    except (ValueError, OSError):
        return False
    try:
        resolved.relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _tree_hash(workspace: Path) -> str:
    """Git-style tree hash for a directory (sorted relative paths + content SHA)."""
    entries: List[Tuple[str, str]] = []
    for fp in sorted(workspace.rglob("*")):
        if fp.is_file():
            rel = str(fp.relative_to(workspace))
            h = sha256_file(fp)
            entries.append((rel, h))
    blob = "\n".join(f"{r}\t{h}" for r, h in entries)
    return sha256_bytes(blob.encode("utf-8"))


def _git_blob(path: Path) -> str:
    """Get git blob hash for a file."""
    try:
        result = subprocess.run(
            ["git", "hash-object", str(path)],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _content_manifest(workspace: Path) -> str:
    """Path-independent content manifest: sorted <SHA256>\\t<relative-path>\\n.

    Fix #13: each line ends with LF.
    """
    entries: List[str] = []
    for fp in sorted(workspace.rglob("*")):
        if fp.is_file():
            rel = str(fp.relative_to(workspace))
            h = sha256_file(fp)
            entries.append(f"{h}\t{rel}")
    # Join with newlines; the final join naturally produces LF-terminated lines
    # when written to a file with write_text (which adds trailing newline).
    return sha256_bytes(("\n".join(entries) + "\n").encode("utf-8"))


def _git_tree(repo: Path, subdir: str) -> str:
    """Get git tree object ID for a subdirectory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD:" + subdir],
            capture_output=True, text=True, check=False, cwd=str(repo),
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# Assertion record
# ---------------------------------------------------------------------------


class Assertion:
    """One assertion in the ASSERTIONS table."""

    def __init__(
        self,
        assertion_id: str,
        requirement: str,
    ):
        self.assertion_id = assertion_id
        self.requirement = requirement
        self.passed: bool = False
        self.details: str = ""
        self.evidence: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.assertion_id,
            "requirement": self.requirement,
            "pass": self.passed,
            "details": self.details,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Validator functions (pure, testable)
# ---------------------------------------------------------------------------


def validate_process_exit(returncode: int) -> Assertion:
    """A01: Process exit code check."""
    a = Assertion("A01-process-exit", ASSERTIONS[0]["requirement"])
    if returncode == 0:
        a.passed = True
        a.details = "Exit code 0"
    else:
        a.passed = False
        a.details = f"Exit code {returncode}"
    return a


def validate_provider_exact(state_data: Dict[str, Any]) -> Assertion:
    """A02: Provider is exactly 'olla'."""
    a = Assertion("A02-provider-exact", ASSERTIONS[1]["requirement"])
    model = state_data.get("model", {})
    prov = model.get("provider")
    if prov == MODEL_PROVIDER:
        a.passed = True
        a.details = f"provider={prov}"
    else:
        a.passed = False
        a.details = f"provider={prov!r}, expected {MODEL_PROVIDER!r}"
    return a


def validate_model_exact(state_data: Dict[str, Any]) -> Assertion:
    """A03: Model is exactly the frozen ID."""
    a = Assertion("A03-model-exact", ASSERTIONS[2]["requirement"])
    model = state_data.get("model", {})
    mid = model.get("id")
    if mid == MODEL_ID:
        a.passed = True
        a.details = f"model={mid}"
    else:
        a.passed = False
        a.details = f"model={mid!r}, expected {MODEL_ID!r}"
    return a


def validate_thinking_off(state_data: Dict[str, Any]) -> Assertion:
    """A04: Thinking level is exactly 'off'."""
    a = Assertion("A04-thinking-off", ASSERTIONS[3]["requirement"])
    tl = state_data.get("thinkingLevel")
    if tl == THINKING_LEVEL:
        a.passed = True
        a.details = f"thinkingLevel={tl}"
    else:
        a.passed = False
        a.details = f"thinkingLevel={tl!r}, expected {THINKING_LEVEL!r}"
    return a


def validate_prompts_count(
    outgoing: List[Dict[str, Any]],
    responses: Dict[str, Dict[str, Any]],
) -> Assertion:
    """A05: Exactly 3 prompt commands sent and responded."""
    a = Assertion("A05-prompts-count", ASSERTIONS[4]["requirement"])
    prompt_cmds = [c for c in outgoing if c.get("type") == "prompt"]
    prompt_responses = {k: v for k, v in responses.items() if k.startswith("prompt_")}

    ids = [c.get("id") for c in prompt_cmds]
    messages = [c.get("message") for c in prompt_cmds]
    a.passed = (
        ids == ["prompt_0", "prompt_1", "prompt_2"]
        and messages == PROMPTS
        and set(prompt_responses) == {"prompt_0", "prompt_1", "prompt_2"}
    )
    a.details = f"prompt_ids={ids}; exact_messages={messages == PROMPTS}; responses={sorted(prompt_responses)}"
    a.evidence.append({"file": "outgoing-commands.jsonl", "line": 1, "prompt_ids": ids})
    return a


REQUIRED_RESPONSE_IDS = {
    "get_state", "get_commands", "prompt_0", "prompt_1", "prompt_2",
    "state_final", "entries_final", "stats_final", "text_final",
}


def validate_response_success(
    responses: Dict[str, Dict[str, Any]],
) -> Assertion:
    """A06: Every required initial, prompt, and final response exists and succeeds."""
    a = Assertion("A06-response-success", ASSERTIONS[5]["requirement"])
    missing = sorted(REQUIRED_RESPONSE_IDS - set(responses))
    failures = sorted(
        rid for rid in REQUIRED_RESPONSE_IDS & set(responses)
        if responses[rid].get("success") is not True
    )
    a.passed = not missing and not failures
    a.details = f"missing={missing}; unsuccessful={failures}"
    a.evidence.append({"file": "rpc-events.jsonl", "line": 1, "required_ids": sorted(REQUIRED_RESPONSE_IDS)})
    return a


def validate_commands_registered(
    commands_response: Optional[Dict[str, Any]],
) -> Assertion:
    """A07: Consortium and focus commands registered with exact sourceInfo paths."""
    a = Assertion("A07-commands-registered", ASSERTIONS[6]["requirement"])
    if commands_response is None or not commands_response.get("success"):
        a.passed = False
        a.details = "get_commands response missing or unsuccessful"
        return a

    cmds = commands_response.get("data", {}).get("commands", [])

    # Check consortium
    consortium_cmd = None
    focus_cmd = None
    for cmd in cmds:
        if cmd.get("name") == "ai-consortium":
            si = cmd.get("sourceInfo", {})
            if si.get("path") != str(CONSORTIUM_EXT):
                a.passed = False
                a.details = f"ai-consortium sourceInfo.path={si.get('path')!r}, expected {str(CONSORTIUM_EXT)!r}"
                return a
            consortium_cmd = cmd
        name = cmd.get("name", "")
        if "focus" in name.lower():
            si = cmd.get("sourceInfo", {})
            source_path = si.get("path")
            try:
                source_matches = Path(str(source_path)).resolve() == FOCUS_EXT.resolve()
            except (OSError, ValueError):
                source_matches = False
            if not source_matches:
                a.passed = False
                a.details = f"focus command sourceInfo.path={source_path!r}, expected same file as {str(FOCUS_EXT)!r}"
                return a
            focus_cmd = cmd

    if consortium_cmd is None:
        a.passed = False
        a.details = "ai-consortium command not registered"
        return a
    if focus_cmd is None:
        a.passed = False
        a.details = "no focus command registered"
        return a

    a.passed = True
    a.details = f"Consortium and focus commands registered with correct sourceInfo paths"
    a.evidence.append({"commands": [c.get("name") for c in cmds]})
    return a


def validate_no_extension_error(rpc_events: List[Dict[str, Any]]) -> Assertion:
    """A08: No extension_error events."""
    a = Assertion("A08-no-extension-error", ASSERTIONS[7]["requirement"])
    errors = [(i + 1, e) for i, e in enumerate(rpc_events) if e.get("type") == "extension_error"]
    if errors:
        a.passed = False
        a.details = f"{len(errors)} extension_error events"
        a.evidence = [{"file": "rpc-events.jsonl", "event_index": idx} for idx, _ in errors]
    else:
        a.passed = True
        a.details = "No extension_error events"
    return a


def validate_protocol_clean(protocol_errors: List[str]) -> Assertion:
    """A09: No protocol errors."""
    a = Assertion("A09-protocol-clean", ASSERTIONS[8]["requirement"])
    if protocol_errors:
        a.passed = False
        a.details = f"{len(protocol_errors)} protocol errors: {'; '.join(protocol_errors[:3])}"
    else:
        a.passed = True
        a.details = "Protocol clean"
    return a


def validate_compaction(all_events: List[Dict[str, Any]]) -> Assertion:
    """A10: No compaction_start; isCompacting always false.

    Fix #5: real get_state response has {type:response, id:..., data:{isCompacting}},
    no 'command' field on some implementations. Check all response events.
    """
    a = Assertion("A10-compaction", ASSERTIONS[9]["requirement"])
    for idx, ev in enumerate(all_events):
        etype = ev.get("type", "")
        if etype == "compaction_start":
            a.passed = False
            a.details = f"compaction_start at event index {idx}"
            a.evidence.append({"file": "rpc-events.jsonl", "event_index": idx + 1})
            return a
        # Check isCompacting in any response data
        if etype == "response":
            data = ev.get("data", {})
            if data.get("isCompacting") is True:
                a.passed = False
                a.details = f"isCompacting==true at event index {idx}"
                a.evidence.append({"file": "rpc-events.jsonl", "event_index": idx + 1})
                return a
    a.passed = True
    a.details = "No compaction detected"
    return a


def validate_confinement(
    rpc_events: List[Dict[str, Any]],
    workspace: Path,
) -> Assertion:
    """A11: Path confinement — tool args must resolve inside workspace only.

    Fix #8: not runtime root, only workspace.
    """
    a = Assertion("A11-confinement", ASSERTIONS[10]["requirement"])
    checked_paths: List[str] = []
    violations: List[str] = []

    def _check_value(obj: Any, depth: int = 0) -> None:
        if depth > 10:
            return
        if isinstance(obj, str):
            if obj.startswith(("/", "./", "../")):
                checked_paths.append(obj)
                if not is_path_in_workspace(obj, workspace):
                    violations.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _check_value(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                _check_value(item, depth + 1)

    for idx, ev in enumerate(rpc_events):
        if ev.get("type") == "tool_execution_start":
            args = ev.get("args", {})
            _check_value(args)

    if violations:
        a.passed = False
        a.details = f"{len(violations)} path violations: {' '.join(violations[:5])}"
        a.evidence = [{"file": "rpc-events.jsonl", "checked_paths": checked_paths, "violations": violations}]
        return a

    a.passed = True
    a.details = f"All {len(checked_paths)} paths confined to workspace"
    a.evidence.append({"file": "rpc-events.jsonl", "checked_paths": checked_paths})
    return a


def _single_edit_operation(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return Pi's single nested edit operation, or None for another schema."""
    edits = args.get("edits")
    if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
        return None
    return edits[0]


def validate_edit_recovery(rpc_events: List[Dict[str, Any]]) -> Assertion:
    """A12: Edit recovery ordered subsequence.

    Fix #7: correlate by toolCallId. Validate:
    1. Failed edit START has exact frozen wrong old/new text
    2. Later read END
    3. Successful edit START has exact actual upload old/new text
    4. Successful edit END result.isError=false
    5. Later final read END
    Count unique tool executions >= 3. Extra tools allowed.
    """
    a = Assertion("A12-edit-recovery", ASSERTIONS[11]["requirement"])

    # Correlate start/end by toolCallId
    starts: Dict[str, Dict[str, Any]] = {}
    ends: Dict[str, Dict[str, Any]] = {}
    exec_order: List[Tuple[str, str]] = []  # (toolCallId, 'start'|'end')

    for ev in rpc_events:
        if ev.get("type") == "tool_execution_start":
            tid = ev.get("toolCallId", "")
            starts[tid] = ev
            exec_order.append((tid, "start"))
        elif ev.get("type") == "tool_execution_end":
            tid = ev.get("toolCallId", "")
            ends[tid] = ev
            exec_order.append((tid, "end"))

    # Count unique executions (completed pairs)
    completed_executions = set()
    for tid in starts:
        if tid in ends:
            completed_executions.add(tid)

    if len(completed_executions) < 3:
        a.passed = False
        a.details = f"Only {len(completed_executions)} completed tool executions; need ≥3"
        return a

    # Find edit executions
    edit_pairs = []
    for tid, ev_start in starts.items():
        if ev_start.get("toolName") == "edit" and tid in ends:
            edit_pairs.append((tid, ev_start, ends[tid]))

    # Find failed edit (result.isError=true)
    failed_edit = None
    success_edit = None
    for tid, ev_start, ev_end in edit_pairs:
        result = ev_end.get("result", {})
        if ev_end.get("isError") is True or result.get("isError") is True:
            if failed_edit is None:
                failed_edit = (tid, ev_start, ev_end)
        elif ev_end.get("isError") is False and result.get("isError") is not True:
            if failed_edit is not None:
                success_edit = (tid, ev_start, ev_end)
                break

    if failed_edit is None:
        a.passed = False
        a.details = "No failed edit found"
        return a

    if success_edit is None:
        a.passed = False
        a.details = "No successful edit after failed edit"
        return a

    # Validate failed edit START has wrong old/new text
    fail_tid, fail_start, fail_end = failed_edit
    fail_op = _single_edit_operation(fail_start.get("args", {}))
    if fail_op is None or fail_op.get("oldText") != WRONG_OLD_TEXT or fail_op.get("newText") != WRONG_NEW_TEXT:
        a.passed = False
        a.details = f"Failed edit operation doesn't match frozen wrong text: operation={fail_op!r}"
        return a

    # Validate successful edit START has correct old/new text
    succ_tid, succ_start, succ_end = success_edit
    succ_op = _single_edit_operation(succ_start.get("args", {}))
    if succ_op is None or succ_op.get("oldText") != CORRECT_OLD_TEXT or succ_op.get("newText") != CORRECT_NEW_TEXT:
        a.passed = False
        a.details = f"Success edit operation doesn't match correct text: operation={succ_op!r}"
        return a

    # Validate successful edit END has isError=false
    succ_result = succ_end.get("result", {})
    if succ_end.get("isError") is not False and succ_result.get("isError") is not False:
        a.passed = False
        a.details = "Successful edit end isError is not false"
        return a

    # Check there's a read between failed and successful edit
    fail_pos = rpc_events.index(fail_start)
    succ_pos = rpc_events.index(succ_start)
    read_between = False
    for ev in rpc_events:
        if ev.get("type") == "tool_execution_end" and ev.get("toolName") == "read":
            pos = rpc_events.index(ev)
            if fail_pos < pos < succ_pos:
                read_between = True
                break

    if not read_between:
        a.passed = False
        a.details = "No read between failed and successful edit"
        return a

    # Check final read after successful edit
    final_reads = [ev for ev in rpc_events if ev.get("type") == "tool_execution_end" and ev.get("toolName") == "read"]
    has_final_read = False
    for fr in final_reads:
        pos = rpc_events.index(fr)
        if pos > succ_pos:
            has_final_read = True
            break

    if not has_final_read:
        a.passed = False
        a.details = "No final read after successful edit"
        return a

    a.passed = True
    a.details = f"Edit recovery OK: {len(completed_executions)} tool executions, failed→read→success→final-read"
    return a


def validate_stage_a_cardinality(
    consortium_events: List[Dict[str, Any]],
) -> Assertion:
    """A13: StageA cardinality with per-deliberation pairing.

    Fix #10: map one deliberation_start/check/telemetry per deliberation.
    First baseline false/false; all later true/false; ≥1 eligible.
    """
    a = Assertion("A13-stage-a-cardinality", ASSERTIONS[12]["requirement"])

    del_starts = [(i, e) for i, e in enumerate(consortium_events) if e.get("type") == "deliberation_start"]
    baseline_checks = [(i, e) for i, e in enumerate(consortium_events) if e.get("type") == "baseline_check"]
    telemetries = [(i, e) for i, e in enumerate(consortium_events) if e.get("type") == "deliberation_telemetry"]

    if len(del_starts) != len(baseline_checks) or len(del_starts) != len(telemetries):
        a.passed = False
        a.details = (
            f"cardinality mismatch: deliberation_start={len(del_starts)} "
            f"baseline_check={len(baseline_checks)} "
            f"deliberation_telemetry={len(telemetries)}"
        )
        a.evidence.append({
            "file": "consortium.jsonl",
            "deliberation_start_events": [i + 1 for i, _ in del_starts],
            "baseline_check_events": [i + 1 for i, _ in baseline_checks],
            "telemetry_events": [i + 1 for i, _ in telemetries],
        })
        return a

    if not del_starts:
        a.passed = False
        a.details = "No deliberation events found"
        return a

    # Check per-deliberation ordering: each trio must be start→check→telemetry in order
    eligible_count = 0
    first_seen = True
    for di, (ds_idx, ds_ev) in enumerate(del_starts):
        bc_idx, bc_ev = baseline_checks[di]
        tel_idx, tel_ev = telemetries[di]

        if not (ds_idx < bc_idx < tel_idx):
            a.passed = False
            a.details = f"Deliberation {di}: order violated (start={ds_idx}, check={bc_idx}, tel={tel_idx})"
            a.evidence.append({
                "file": "consortium.jsonl",
                "deliberation_index": di,
                "event_indexes": {"start": ds_idx + 1, "check": bc_idx + 1, "telemetry": tel_idx + 1},
            })
            return a

        ba = bc_ev.get("baseline_available", False)
        bs = bc_ev.get("baseline_supplied", False)

        if first_seen:
            if ba is not False or bs is not False:
                a.passed = False
                a.details = f"First baseline_check must be false/false, got {ba}/{bs}"
                a.evidence.append({
                    "file": "consortium.jsonl",
                    "event_index": bc_idx + 1,
                })
                return a
            first_seen = False
        else:
            if ba is not True or bs is not False:
                a.passed = False
                a.details = f"Baseline {di} must be true/false, got {ba}/{bs}"
                a.evidence.append({
                    "file": "consortium.jsonl",
                    "event_index": bc_idx + 1,
                })
                return a

        if tel_ev.get("baseline_available") != ba or tel_ev.get("baseline_supplied") != bs:
            a.passed = False
            a.details = f"Deliberation {di}: baseline_check and telemetry flags differ"
            a.evidence.append({"file": "consortium.jsonl", "event_indexes": [bc_idx + 1, tel_idx + 1]})
            return a
        if di + 1 < len(del_starts) and tel_idx >= del_starts[di + 1][0]:
            a.passed = False
            a.details = f"Deliberation {di}: telemetry crosses into next deliberation"
            return a
        if ba:
            eligible_count += 1

    if eligible_count < 1:
        a.passed = False
        a.details = "At least one eligible baseline_check required"
        return a

    a.passed = True
    a.details = f"{len(del_starts)} deliberations paired; {eligible_count} eligible"
    a.evidence.append({
        "file": "consortium.jsonl",
        "deliberation_count": len(del_starts),
        "eligible_count": eligible_count,
    })
    return a


def validate_usage_honesty(
    consortium_events: List[Dict[str, Any]],
) -> Assertion:
    """A14: Usage honesty with real allowed statuses.

    Fix #6: allowed statuses complete|partial|unreported|not_applicable.
    aggregate_usage allowed only on complete, required when complete and successful_calls>0.
    probe_complete usage shape from runtime31.
    """
    a = Assertion("A14-usage-honesty", ASSERTIONS[13]["requirement"])
    errors: List[str] = []
    VALID_STATUSES = {"complete", "partial", "unreported", "not_applicable"}

    for idx, ev in enumerate(consortium_events):
        if ev.get("type") == "probe_complete":
            ur = ev.get("usage_reported")
            if not isinstance(ur, bool):
                errors.append(f"[{idx}] usage_reported not boolean: {ur!r}")
            usage = ev.get("usage")
            if ur and usage is None:
                errors.append(f"[{idx}] usage_reported=true but no usage")
            if not ur and usage is not None:
                errors.append(f"[{idx}] usage_reported=false but has usage")
        if ev.get("type") == "deliberation_telemetry":
            status = ev.get("usage_status")
            if status not in VALID_STATUSES:
                errors.append(f"[{idx}] invalid usage_status: {status!r}")
            sc = ev.get("successful_calls", 0)
            agg = ev.get("aggregate_usage")
            if status == "complete" and isinstance(sc, int) and sc > 0 and agg is None:
                errors.append(f"[{idx}] complete with successful_calls>{0} but no aggregate_usage")
            if status != "complete" and agg is not None:
                errors.append(f"[{idx}] aggregate_usage on non-complete status")

    if errors:
        a.passed = False
        a.details = "; ".join(errors[:5])
        a.evidence.append({"file": "consortium.jsonl", "errors": errors})
        return a
    a.passed = True
    a.details = "All usage fields consistent"
    return a


def validate_m6(
    consortium_events: List[Dict[str, Any]],
    scripted_prompt_count: Optional[int] = None,
) -> Tuple[Assertion, Dict[str, Any]]:
    """A15: V6 M6 injection outcome rate."""
    a = Assertion("A15-M6-injection-rate", ASSERTIONS[14]["requirement"])
    completions = [e for e in consortium_events if e.get("type") == "injection_complete"]
    skips = [e for e in consortium_events if e.get("type") == "injection_skipped"]
    complete = len(completions)
    skipped = len(skips)
    denom = complete + skipped

    reasons: Dict[str, int] = {}
    reason_schema_failures: List[str] = []
    for idx, ev in enumerate(skips):
        r = ev.get("reason")
        if r is None:
            r = "<missing>"
        elif not isinstance(r, str):
            reason_schema_failures.append(f"skip[{idx}].reason is not a string")
            r = "<invalid>"
        reasons[r] = reasons.get(r, 0) + 1
    if not skips:
        reasons["<missing>"] = 0

    turn_starts = [e for e in consortium_events if e.get("type") == "turn_start"]
    del_starts = [e for e in consortium_events if e.get("type") == "deliberation_start"]

    result: Dict[str, Any] = {
        "complete": complete,
        "skipped": skipped,
        "denominator": denom,
        "rate": round(complete / denom, 6) if denom > 0 else None,
        "rate_label": "not_applicable" if denom == 0 else f"{complete}/{denom}",
        "skip_reason_histogram": reasons,
        "turn_start_count": len(turn_starts),
        "deliberation_start_count": len(del_starts),
        "scripted_prompt_count": len(PROMPTS) if scripted_prompt_count is None else scripted_prompt_count,
        "schema_failures": reason_schema_failures,
    }

    a.evidence.append({"file": "consortium/", "line": 1, "metrics": result})
    if reason_schema_failures:
        a.passed = False
        a.details = "; ".join(reason_schema_failures)
        return a, result
    if denom == 0:
        a.passed = False
        a.details = "denominator == 0 → not_applicable (fails completeness gate)"
        return a, result

    a.passed = True
    a.details = f"M6 = {complete}/{denom} = {result['rate']}"
    return a, result


def validate_m7a(
    consortium_events: List[Dict[str, Any]],
    run_wall_clock_ms: float,
) -> Tuple[Assertion, Dict[str, Any]]:
    """A16: V6 M7a nearest-rank percentile latency per modelKey."""
    a = Assertion("A16-M7a-latency", ASSERTIONS[15]["requirement"])
    groups: Dict[str, List[float]] = {}
    schema_failures: List[str] = []

    for idx, ev in enumerate(consortium_events):
        if ev.get("type") != "probe_complete":
            continue
        mk = ev.get("modelKey")
        dur = ev.get("duration_ms")
        if not isinstance(mk, str) or not mk:
            schema_failures.append(f"[{idx}] modelKey missing/non-string")
            continue
        if dur is None or isinstance(dur, bool) or not isinstance(dur, (int, float)):
            schema_failures.append(f"[{idx}] modelKey={mk}: duration_ms missing/non-numeric")
            continue
        if math.isnan(dur) or math.isinf(dur) or dur < 0:
            schema_failures.append(f"[{idx}] modelKey={mk}: duration_ms invalid {dur}")
            continue
        groups.setdefault(mk, []).append(float(dur))

    result: Dict[str, Any] = {"groups": {}, "run_wall_clock_ms": round(run_wall_clock_ms, 1)}
    if schema_failures:
        a.passed = False
        a.details = "Schema failures: " + "; ".join(schema_failures[:5])
        result["schema_failures"] = schema_failures
        a.evidence.append({"file": "consortium/", "line": 1, "metrics": result})
        return a, result

    if not groups:
        a.passed = False
        a.details = "No probe_complete latency groups"
        a.evidence.append({"file": "consortium/", "line": 1, "metrics": result})
        return a, result

    for mk, durations in sorted(groups.items()):
        durations.sort()
        n = len(durations)
        p50_idx = max(0, math.ceil(0.50 * n) - 1)
        p95_idx = max(0, math.ceil(0.95 * n) - 1)
        result["groups"][mk] = {
            "n": n,
            "min": durations[0],
            "max": durations[-1],
            "p50": durations[p50_idx],
            "p95": durations[p95_idx],
        }

    a.passed = True
    a.details = f"{len(groups)} modelKey groups validated"
    a.evidence.append({"file": "consortium/", "line": 1, "metrics": result})
    return a, result


def _strip_fences(text: str) -> str:
    """Strip one leading ```json or ``` fence with optional newline, and trailing ```."""
    s = text.strip()
    s = re.sub(r"^```(?:json)?\n?", "", s, count=1, flags=re.IGNORECASE)
    s = re.sub(r"\n?```$", "", s, count=1, flags=re.IGNORECASE)
    return s.strip()


def classify_extraction_output(raw_output: str) -> str:
    """V6 M7b: classify raw extraction output as invalid/empty/nonempty."""
    stripped = _strip_fences(raw_output)
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return "invalid"
    if not isinstance(parsed, dict):
        return "invalid"

    for k in VECTOR_KEYS:
        if k in parsed:
            v = parsed[k]
            if v is not None and not isinstance(v, (str, list)):
                return "invalid"

    def _normalize_empty(val: Any) -> bool:
        if val is None:
            return True
        if isinstance(val, str):
            return val.strip() == ""
        if isinstance(val, list):
            return all(str(item).strip() == "" for item in val)
        return False

    all_empty = all(_normalize_empty(parsed.get(k)) for k in VECTOR_KEYS)
    if all_empty:
        return "empty"
    return "nonempty"


def validate_m7b(
    consortium_events: List[Dict[str, Any]],
) -> Tuple[Assertion, Dict[str, Any]]:
    """A17: V6 M7b extraction output classification."""
    a = Assertion("A17-M7b-extraction", ASSERTIONS[16]["requirement"])
    counts = {"invalid": 0, "empty": 0, "nonempty": 0, "total": 0}

    for ev in consortium_events:
        if ev.get("type") != "probe_complete" or ev.get("modelKey") != "extraction":
            continue
        counts["total"] += 1
        raw = ev.get("output", "")
        cls = classify_extraction_output(raw)
        counts[cls] += 1

    a.passed = counts["total"] > 0
    a.details = (
        f"total={counts['total']} invalid={counts['invalid']} "
        f"empty={counts['empty']} nonempty={counts['nonempty']}"
    )
    a.evidence.append({"file": "consortium/", "line": 1, "metrics": counts})
    return a, counts


def validate_m8(stats_response: Optional[Dict[str, Any]]) -> Assertion:
    """A18: V6 M8 session token totals."""
    a = Assertion("A18-M8-tokens", ASSERTIONS[17]["requirement"])
    if stats_response is None or not stats_response.get("success"):
        a.passed = False
        a.details = "get_session_stats response missing or unsuccessful"
        return a

    tokens = stats_response.get("data", {}).get("tokens")
    if tokens is None:
        a.passed = False
        a.details = "tokens object absent in stats response"
        return a

    required_keys = ["input", "output", "cacheRead", "cacheWrite", "total"]
    vals: Dict[str, float] = {}
    for k in required_keys:
        v = tokens.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            a.passed = False
            a.details = f"tokens.{k} is not numeric: {v!r}"
            return a
        vals[k] = float(v)

    expected_total = vals["input"] + vals["output"] + vals["cacheRead"] + vals["cacheWrite"]
    if abs(vals["total"] - expected_total) > 0.001:
        a.passed = False
        a.details = (
            f"total({vals['total']}) != "
            f"input({vals['input']})+output({vals['output']})+"
            f"cacheRead({vals['cacheRead']})+cacheWrite({vals['cacheWrite']})"
            f"={expected_total}"
        )
        return a

    a.passed = True
    a.details = f"total={vals['total']} = input+output+cacheRead+cacheWrite"
    a.evidence.append({"file": "stats_final.json", "line": 1, "tokens": vals})
    return a


def validate_fixture(contents: str) -> Assertion:
    """A19: Final fixture marker unchanged, expected new line present, old actual line absent."""
    a = Assertion("A19-fixture-marker", ASSERTIONS[18]["requirement"])
    errors: List[str] = []

    if RELEASE_TAG_VALUE not in contents:
        errors.append(f"RELEASE_TAG {RELEASE_TAG_VALUE!r} not found")
    if UNCHANGED_MARKER not in contents:
        errors.append(f"Unchanged marker {UNCHANGED_MARKER!r} not found")
    if CORRECT_NEW_TEXT not in contents:
        errors.append(f"New upload line {CORRECT_NEW_TEXT!r} not found")
    if CORRECT_OLD_TEXT in contents:
        errors.append(f"Old upload line {CORRECT_OLD_TEXT!r} still present")

    a.passed = len(errors) == 0
    if errors:
        a.details = "; ".join(errors)
    else:
        a.details = "Fixture marker intact; old line replaced by new upload line"
    a.evidence.append({"file": "fixture-after/RELEASE_NOTES.txt", "line": 1})
    return a


def validate_final_text(text: str) -> Assertion:
    """A20: Final assistant text contains marker + new line."""
    a = Assertion("A20-final-text", ASSERTIONS[19]["requirement"])
    errors: List[str] = []
    if RELEASE_TAG_VALUE not in text:
        errors.append(f"RELEASE_TAG {RELEASE_TAG_VALUE!r} not in final text")
    if CORRECT_NEW_TEXT not in text:
        errors.append(f"New upload line not in final text")
    a.passed = len(errors) == 0
    a.details = "Final text contains marker and new line" if a.passed else "; ".join(errors)
    a.evidence.append({"file": "text_final.json", "line": 1})
    return a


def validate_path_diff(
    workspace: Path,
    template_workspace: Path,
) -> Assertion:
    """A21: Objective path diff only RELEASE_NOTES modified; .pi ignored."""
    a = Assertion("A21-path-diff", ASSERTIONS[20]["requirement"])
    modified: List[str] = []
    for fp in sorted(workspace.rglob("*")):
        if not fp.is_file():
            continue
        rel = str(fp.relative_to(workspace))
        if rel.startswith(".pi/"):
            continue
        tmpl_fp = template_workspace / rel
        if not tmpl_fp.exists():
            modified.append(rel)
            continue
        if fp.read_bytes() != tmpl_fp.read_bytes():
            modified.append(rel)

    expected_modified = {"RELEASE_NOTES.txt"}
    actual = set(modified)
    if actual == expected_modified:
        a.passed = True
        a.details = "Only RELEASE_NOTES.txt modified (excluding .pi)"
    else:
        a.passed = False
        a.details = f"Modified: {actual}; expected: {expected_modified}"
    a.evidence.append({"file": "fixture-after.diff", "line": 1, "modified": sorted(actual)})
    return a


# ---------------------------------------------------------------------------
# Build PI command
# ---------------------------------------------------------------------------


def build_pi_command(
    run_id: str,
    repetition: int,
    workspace: Path,
    sessions_dir: Path,
) -> List[str]:
    """Build the exact argv for pi --mode rpc."""
    return [
        "pi",
        "--mode", "rpc",
        "--no-context-files",
        "--no-skills",
        "--no-prompt-templates",
        "--no-extensions",
        "--tools", "read,edit,grep,find,ls",
        "-e", str(PROVIDER_EXT),
        "-e", str(CONSORTIUM_EXT),
        "-e", str(FOCUS_EXT),
        "--provider", MODEL_PROVIDER,
        "--model", MODEL_ID,
        "--thinking", THINKING_LEVEL,
        "--dm-off",
        "--write-guard", str(workspace),
        "--approve",
        "--session-dir", str(sessions_dir),
        "--name", f"phase05-{run_id}-rep{repetition}",
    ]


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def _read_package_version(package_json: Path) -> str:
    try:
        return str(json.loads(package_json.read_text()).get("version", "MISSING"))
    except Exception:
        return "MISSING"


def _command_value(command: List[str], cwd: Path) -> Tuple[Dict[str, Any], str]:
    record = cmd_output(command, cwd=cwd)
    return record, record["output"].strip() if record["exit_code"] == 0 else ""


def validate_manifest_identities(manifest: Dict[str, Any]) -> Assertion:
    """A22: every frozen identity check must be true before a live prompt."""
    a = Assertion("A22-frozen-identities", ASSERTIONS[21]["requirement"])
    checks = manifest.get("identity_checks", {})
    failed = sorted(name for name, passed in checks.items() if passed is not True)
    a.passed = bool(checks) and not failed
    a.details = f"{len(checks) - len(failed)}/{len(checks)} identity checks pass; failed={failed}"
    a.evidence.append({"file": "manifest.json", "line": 1, "failed_checks": failed})
    return a


def build_manifest(
    run_id: str,
    repetition: int,
    workspace: Path,
    runtime_root: Path,
    pi_command: List[str],
) -> Dict[str, Any]:
    """Build and evaluate the complete frozen identity manifest."""
    runner_commit_rec, runner_commit = _command_value(["git", "rev-parse", "HEAD"], REPO_ROOT)
    runner_status = cmd_output(["git", "status", "--short"], cwd=REPO_ROOT)

    source_v2_raw = cmd_output(
        ["git", "ls-tree", "-r", STAGE_A_COMMIT, "--",
         "index.ts", "src", "package.json", "package-lock.json", "tsconfig.json"],
        cwd=REPO_ROOT,
    )
    source_v2_actual = (
        sha256_bytes(source_v2_raw["output"].encode("utf-8"))
        if source_v2_raw["exit_code"] == 0 else ""
    )

    v5_path = CONCEPT_REPO / "docs" / "behavioral-preregistration-2026-07-28.md"
    v6_path = CONCEPT_REPO / "docs" / "behavioral-preregistration-2026-07-29.md"
    v5_blob_rec, v5_blob = _command_value(
        ["git", "rev-parse", "HEAD:docs/behavioral-preregistration-2026-07-28.md"], CONCEPT_REPO
    )
    v6_blob_rec, v6_blob = _command_value(
        ["git", "rev-parse", "HEAD:docs/behavioral-preregistration-2026-07-29.md"], CONCEPT_REPO
    )

    provider_repo = PROVIDER_EXT.parent
    focus_repo = FOCUS_EXT.parent
    provider_commit_rec, provider_commit = _command_value(["git", "rev-parse", "HEAD"], provider_repo)
    focus_commit_rec, focus_commit = _command_value(["git", "rev-parse", "HEAD"], focus_repo)
    provider_status = cmd_output(["git", "status", "--short"], cwd=provider_repo)
    focus_status = cmd_output(["git", "status", "--short"], cwd=focus_repo)

    provider_blob = _git_blob(PROVIDER_EXT) if PROVIDER_EXT.exists() else "MISSING"
    focus_blob = _git_blob(FOCUS_EXT) if FOCUS_EXT.exists() else "MISSING"
    consortium_blob = _git_blob(CONSORTIUM_EXT) if CONSORTIUM_EXT.exists() else "MISSING"
    provider_sha = sha256_file(PROVIDER_EXT) if PROVIDER_EXT.exists() else "MISSING"
    focus_sha = sha256_file(FOCUS_EXT) if FOCUS_EXT.exists() else "MISSING"
    consortium_sha = sha256_file(CONSORTIUM_EXT) if CONSORTIUM_EXT.exists() else "MISSING"

    p00_template_tree_actual = _git_tree(REPO_ROOT, ".parcour-runs-templates/p00-smoke-readonly")
    p00_workspace_tree_actual = _git_tree(REPO_ROOT, ".parcour-runs-templates/p00-smoke-readonly/workspace")

    pi_version_rec = cmd_output(["pi", "--version"])
    node_version_rec = cmd_output(["node", "--version"])
    package_versions = {
        "pi-ai": _read_package_version(REPO_ROOT / "node_modules/@earendil-works/pi-ai/package.json"),
        "pi-agent-core": _read_package_version(REPO_ROOT / "node_modules/@earendil-works/pi-agent-core/package.json"),
        "pi-coding-agent": _read_package_version(REPO_ROOT / "node_modules/@earendil-works/pi-coding-agent/package.json"),
        "provider": _read_package_version(provider_repo / "package.json"),
        "focus": _read_package_version(focus_repo / "package.json"),
    }

    v5_file_sha = sha256_file(v5_path) if v5_path.exists() else "MISSING"
    v6_file_sha = sha256_file(v6_path) if v6_path.exists() else "MISSING"
    provider_status_lines = provider_status["output"].splitlines()
    focus_status_lines = focus_status["output"].splitlines()

    identity_checks = {
        "implementation_clean": runner_status["exit_code"] == 0 and not runner_status["output"].strip(),
        "v5_blob": v5_blob == V5_BLOB_SHA,
        "v5_file_sha256": v5_file_sha == V5_FILE_SHA256,
        "v6_blob": v6_blob == V6_BLOB_SHA,
        "v6_file_sha256": v6_file_sha == V6_FILE_SHA256,
        "provider_commit": provider_commit == PROVIDER_EXPECTED_COMMIT,
        "provider_blob": provider_blob == PROVIDER_EXPECTED_BLOB,
        "provider_sha256": provider_sha == PROVIDER_EXPECTED_SHA256,
        "provider_version": package_versions["provider"] == PROVIDER_PACKAGE_VERSION,
        "provider_dirty_state": provider_status_lines == [" M package-lock.json"],
        "focus_commit": focus_commit == FOCUS_EXPECTED_COMMIT,
        "focus_blob": focus_blob == FOCUS_EXPECTED_BLOB,
        "focus_sha256": focus_sha == FOCUS_EXPECTED_SHA256,
        "focus_version": package_versions["focus"] == FOCUS_PACKAGE_VERSION,
        "focus_dirty_state": focus_status_lines == [" M package-lock.json"],
        "consortium_blob": consortium_blob == CONSORTIUM_INDEX_BLOB,
        "consortium_sha256": consortium_sha == CONSORTIUM_INDEX_SHA256,
        "source_v2": source_v2_actual == STAGE_A_SOURCE_V2_SHA256,
        "p00_template_tree": p00_template_tree_actual == P00_TEMPLATE_TREE,
        "p00_workspace_tree": p00_workspace_tree_actual == P00_WORKSPACE_TREE,
        "pi_version": pi_version_rec["exit_code"] == 0 and pi_version_rec["output"].strip() == PI_VERSION,
        "node_version": node_version_rec["exit_code"] == 0 and node_version_rec["output"].strip() == NODE_VERSION,
        "pi_package_versions": all(
            package_versions[name] == PI_PACKAGE_VERSION
            for name in ("pi-ai", "pi-agent-core", "pi-coding-agent")
        ),
    }

    return {
        "run_id": run_id,
        "repetition": repetition,
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
        "started_at_unix": time.time(),
        "workspace": str(workspace),
        "runtime_root": str(runtime_root),
        "argv": pi_command,
        "runner_commit": runner_commit_rec,
        "runner_status": runner_status,
        "concept_commit": cmd_output(["git", "rev-parse", "HEAD"], cwd=CONCEPT_REPO),
        "concept_status": cmd_output(["git", "status", "--short"], cwd=CONCEPT_REPO),
        "frozen": {
            "v5": {"path": str(v5_path), "expected_blob": V5_BLOB_SHA, "actual_blob": v5_blob,
                   "blob_command": v5_blob_rec, "expected_sha256": V5_FILE_SHA256, "actual_sha256": v5_file_sha},
            "v6": {"path": str(v6_path), "expected_blob": V6_BLOB_SHA, "actual_blob": v6_blob,
                   "blob_command": v6_blob_rec, "expected_sha256": V6_FILE_SHA256, "actual_sha256": v6_file_sha},
            "source_v2": {"commit": STAGE_A_COMMIT, "expected_sha256": STAGE_A_SOURCE_V2_SHA256,
                          "actual_sha256": source_v2_actual, "raw": source_v2_raw},
            "p00": {"expected_template_tree": P00_TEMPLATE_TREE, "actual_template_tree": p00_template_tree_actual,
                    "expected_workspace_tree": P00_WORKSPACE_TREE, "actual_workspace_tree": p00_workspace_tree_actual},
        },
        "extensions": {
            "provider": {"path": str(PROVIDER_EXT), "commit": provider_commit, "commit_command": provider_commit_rec,
                         "blob": provider_blob, "sha256": provider_sha, "version": package_versions["provider"],
                         "status": provider_status},
            "consortium": {"path": str(CONSORTIUM_EXT), "blob": consortium_blob, "sha256": consortium_sha},
            "focus": {"path": str(FOCUS_EXT), "commit": focus_commit, "commit_command": focus_commit_rec,
                      "blob": focus_blob, "sha256": focus_sha, "version": package_versions["focus"],
                      "status": focus_status},
        },
        "runtime_versions": {"pi": pi_version_rec, "node": node_version_rec, "packages": package_versions},
        "identity_checks": identity_checks,
        "template_content_manifest": _content_manifest(TEMPLATE_WORKSPACE),
        "workspace_content_manifest_before": _content_manifest(workspace),
    }


# ---------------------------------------------------------------------------
# Runner core
# ---------------------------------------------------------------------------

class RpcSequencer:
    """Pure three-prompt RPC state machine used by the live loop and tests."""

    def __init__(self) -> None:
        self.responses: Dict[str, Dict[str, Any]] = {}
        self.prompts_sent = 0
        self.settles_handled = 0
        self.final_queries_sent = False
        self.complete = False
        self.errors: List[str] = []

    def on_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        if event.get("type") == "response" and event.get("id"):
            self.responses[str(event["id"])] = event

        if self.prompts_sent == 0 and {"get_state", "get_commands"}.issubset(self.responses):
            if all(self.responses[rid].get("success") is True for rid in ("get_state", "get_commands")):
                actions.append({"id": "prompt_0", "type": "prompt", "message": PROMPTS[0]})
                self.prompts_sent = 1
            elif not self.errors:
                self.errors.append("initial get_state/get_commands response unsuccessful")

        if event.get("type") == "agent_settled":
            if self.prompts_sent == 0:
                self.errors.append("agent_settled before prompt_0")
            elif self.settles_handled >= self.prompts_sent:
                self.errors.append("unexpected duplicate agent_settled")
            else:
                self.settles_handled += 1
                if self.settles_handled < len(PROMPTS):
                    idx = self.settles_handled
                    actions.append({"id": f"prompt_{idx}", "type": "prompt", "message": PROMPTS[idx]})
                    self.prompts_sent += 1
                elif self.settles_handled == len(PROMPTS) and not self.final_queries_sent:
                    actions.extend([
                        {"id": "state_final", "type": "get_state"},
                        {"id": "entries_final", "type": "get_entries"},
                        {"id": "stats_final", "type": "get_session_stats"},
                        {"id": "text_final", "type": "get_last_assistant_text"},
                    ])
                    self.final_queries_sent = True

        final_ids = {"state_final", "entries_final", "stats_final", "text_final"}
        if self.final_queries_sent and final_ids.issubset(self.responses):
            self.complete = True
        return actions


class Phase05Runner:
    """Phase 0.5 runner: one run per invocation."""

    def __init__(
        self,
        run_id: str,
        repetition: int,
    ):
        self.run_id = run_id
        self.repetition = repetition
        self.tmp_root = Path("/tmp") / f"parcour-{run_id}"
        self.workspace = self.tmp_root / "workspace"
        self.sessions_dir = self.tmp_root / "sessions"
        self.runtime_root = self.tmp_root
        self.evidence_dir = REPO_ROOT / ".parcour-runs" / run_id

        # Collected data
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
        self.wall_clock_ms: float = 0.0
        self.manifest: Dict[str, Any] = {}
        self.exception_info: Optional[str] = None
        self.timeout_occurred: bool = False
        self.harvest_allowed: bool = False
        self.metric_results: Dict[str, Any] = {}
        self.identity_preflight: Optional[Assertion] = None

    def _validate_run_id(self) -> None:
        """Validate run_id is safe (alphanumeric + hyphens only)."""
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*$", self.run_id):
            raise ValueError(f"Invalid run_id: {self.run_id!r}")

    def _guard_existing_paths(self) -> None:
        """R2: refuse if any target path already exists."""
        targets = [
            (self.tmp_root, "tmp parcour dir"),
            (self.workspace, "workspace"),
            (self.evidence_dir, "evidence dir"),
        ]
        for p, label in targets:
            if p.exists():
                raise FileExistsError(f"Refusing: {label} already exists at {p}")

    def _materialize_workspace(self) -> None:
        """Materialize committed p00 workspace and verify against Git tree.

        Fix #13: verify copied bytes against Git tree/committed template.
        """
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)

        # Copy template workspace files
        for src in TEMPLATE_WORKSPACE.rglob("*"):
            if src.is_file():
                dst = self.workspace / src.relative_to(TEMPLATE_WORKSPACE)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))

        # Verify against committed Git tree
        tmpl_tree = _git_tree(REPO_ROOT, ".parcour-runs-templates/p00-smoke-readonly/workspace")
        if tmpl_tree != P00_WORKSPACE_TREE:
            raise RuntimeError(f"Template workspace tree {tmpl_tree} != expected {P00_WORKSPACE_TREE}")

        # Verify copied bytes match template
        for src in TEMPLATE_WORKSPACE.rglob("*"):
            if src.is_file():
                dst = self.workspace / src.relative_to(TEMPLATE_WORKSPACE)
                if dst.read_bytes() != src.read_bytes():
                    raise RuntimeError(f"Copied file {dst} differs from template {src}")

        # Verify content manifest
        cm = _content_manifest(self.workspace)
        expected_cm = _content_manifest(TEMPLATE_WORKSPACE)
        if cm != expected_cm:
            raise RuntimeError(f"Content manifest mismatch: {cm} != {expected_cm}")

    def _build_manifest(self) -> Dict[str, Any]:
        pi_command = build_pi_command(
            self.run_id, self.repetition, self.workspace, self.sessions_dir
        )
        self.manifest = build_manifest(
            self.run_id, self.repetition,
            self.workspace, self.runtime_root,
            pi_command,
        )
        return self.manifest

    def run(self) -> Dict[str, Any]:
        """Execute the full Phase 0.5 run. Returns result dict."""
        try:
            self._validate_run_id()
            self._guard_existing_paths()
            self.harvest_allowed = True
            self._materialize_workspace()
            manifest = self._build_manifest()
            self.identity_preflight = validate_manifest_identities(manifest)
            if not self.identity_preflight.passed:
                raise RuntimeError(self.identity_preflight.details)

            pi_command = build_pi_command(
                self.run_id, self.repetition, self.workspace, self.sessions_dir
            )

            stderr_path = self.tmp_root / "rpc-stderr.log"
            rpc_log_path = self.tmp_root / "rpc-events.jsonl"

            start_mono = time.monotonic()
            proc = self._spawn_pi(pi_command, stderr_path)

            try:
                self._run_rpc_loop(proc, rpc_log_path, stderr_path)
            finally:
                self._cleanup_process(proc)
                self.wall_clock_ms = (time.monotonic() - start_mono) * 1000

            # Collect consortium and session logs
            self._collect_consortium_logs()
            self._collect_session_logs()
            manifest.update({
                "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
                "wall_clock_ms": round(self.wall_clock_ms, 1),
                "process_returncode": self.process_returncode,
                "live_boundary_timestamp": self.live_boundary_ts,
                "workspace_content_manifest_after": _content_manifest(self.workspace),
            })

            # Run validations
            assertions = self._validate_all()
            result = self._build_result(assertions, manifest)

        except Exception as exc:
            self.exception_info = f"{type(exc).__name__}: {exc}"
            self.protocol_errors.append(self.exception_info)
            # Build partial result with whatever we have
            manifest = getattr(self, 'manifest', {})
            assertions = self._validate_all()
            result = self._build_result(assertions, manifest)
            result["exception"] = self.exception_info

        # Harvest partial or complete evidence only after the non-reuse guard passed.
        if self.harvest_allowed:
            try:
                self._harvest_evidence(result, self.manifest)
            except Exception as harvest_exc:
                message = f"Harvest failed: {harvest_exc}"
                self.protocol_errors.append(message)
                result["pass"] = False
                result["harvest_error"] = message
        return result

    def _spawn_pi(
        self,
        command: List[str],
        stderr_path: Path,
    ) -> subprocess.Popen:
        """Spawn pi subprocess. stderr → file directly (no pipe deadlock).

        Fix #2: start_new_session=True.
        """
        stderr_handle = stderr_path.open("wb")
        proc = subprocess.Popen(
            command,
            cwd=str(self.workspace),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
            env={**os.environ, "PI_SKIP_VERSION_CHECK": "1"},
            start_new_session=True,  # Fix #2
        )
        proc._stderr_handle = stderr_handle  # type: ignore[attr-defined]
        return proc

    def _record_direction(self, direction: str, payload: Dict[str, Any]) -> None:
        self.direction_sequence += 1
        self.directional_records.append({
            "seq": self.direction_sequence,
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "direction": direction,
            "payload": copy.deepcopy(payload),
        })

    def _send(self, proc: subprocess.Popen, payload: Dict[str, Any]) -> None:
        """Send and durably record one JSON-RPC command."""
        assert proc.stdin is not None
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        proc.stdin.write(line)
        proc.stdin.flush()
        self.outgoing_commands.append(copy.deepcopy(payload))
        record = {"ts": datetime.datetime.utcnow().isoformat() + "Z", "payload": copy.deepcopy(payload)}
        self.outgoing_records.append(record)
        self._record_direction("in", payload)

    def _run_rpc_loop(
        self,
        proc: subprocess.Popen,
        rpc_log_path: Path,
        stderr_path: Path,
    ) -> None:
        """Drive the frozen RPC sequence through the pure RpcSequencer."""
        assert proc.stdin is not None
        assert proc.stdout is not None

        buffer = b""
        total_start = time.monotonic()
        active_turn_start: Optional[float] = None
        sequencer = RpcSequencer()
        reported_sequence_errors = 0

        self._send(proc, {"id": "get_state", "type": "get_state"})
        self._send(proc, {"id": "get_commands", "type": "get_commands"})

        with rpc_log_path.open("wb") as rpc_log:
            while not sequencer.complete:
                elapsed_total = time.monotonic() - total_start
                if elapsed_total > TIMEOUT_SECONDS * len(PROMPTS):
                    self.timeout_occurred = True
                    self.protocol_errors.append(f"Total timeout after {elapsed_total:.1f}s")
                    self._terminate_process_group(proc)
                    break
                if active_turn_start is not None:
                    elapsed_turn = time.monotonic() - active_turn_start
                    if elapsed_turn > TIMEOUT_SECONDS:
                        self.timeout_occurred = True
                        self.protocol_errors.append(f"Per-turn timeout after {elapsed_turn:.1f}s")
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
                    raw_line, buffer = buffer.split(b"\n", 1)
                    if raw_line.endswith(b"\r"):
                        raw_line = raw_line[:-1]
                    if not raw_line:
                        continue
                    raw_str = raw_line.decode("utf-8", errors="replace")
                    self.raw_incoming.append(raw_str)
                    try:
                        event = json.loads(raw_str)
                    except json.JSONDecodeError as exc:
                        self.protocol_errors.append(
                            f"Invalid JSON at raw line {len(self.raw_incoming)}: {exc}: {raw_str[:200]!r}"
                        )
                        continue

                    self.rpc_events.append(event)
                    self._record_direction("out", event)
                    eid = event.get("id")
                    if event.get("type") == "response" and eid:
                        self.responses[str(eid)] = event

                    actions = sequencer.on_event(event)
                    if len(sequencer.errors) > reported_sequence_errors:
                        self.protocol_errors.extend(sequencer.errors[reported_sequence_errors:])
                        reported_sequence_errors = len(sequencer.errors)
                    if sequencer.errors:
                        break

                    if event.get("type") == "agent_settled":
                        active_turn_start = None
                    for action in actions:
                        if action.get("type") == "prompt":
                            if action.get("id") == "prompt_0" and self.live_boundary_ts is None:
                                self.live_boundary_ts = datetime.datetime.utcnow().isoformat() + "Z"
                                (self.tmp_root / "live-boundary.json").write_text(
                                    json.dumps({"run_id": self.run_id, "repetition": self.repetition,
                                                "sent_prompt": "prompt_0", "ts": self.live_boundary_ts}, indent=2) + "\n"
                                )
                            active_turn_start = time.monotonic()
                        self._send(proc, action)
                    if sequencer.complete:
                        break
                if sequencer.errors or sequencer.complete:
                    break

        if buffer.strip():
            self.protocol_errors.append(f"Unterminated stdout bytes: {buffer[:200]!r}")
        if not sequencer.complete and not self.timeout_occurred and not sequencer.errors:
            self.protocol_errors.append("RPC stream ended before final responses completed")

        try:
            proc.stdin.close()
        except Exception:
            pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.protocol_errors.append("Pi did not exit within 30s after stdin close")
                self._terminate_process_group(proc)

        try:
            proc._stderr_handle.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        if stderr_path.exists():
            self.stderr_lines = stderr_path.read_text(errors="replace").splitlines()
        self.process_returncode = proc.returncode

    def _terminate_process_group(self, proc: subprocess.Popen) -> None:
        """Terminate the entire process group on timeout."""
        try:
            os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
        except (ProcessLookupError, OSError):
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def _cleanup_process(self, proc: subprocess.Popen) -> None:
        """Ensure process is cleaned up."""
        try:
            proc.stdin.close()
        except Exception:
            pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._terminate_process_group(proc)
        self.process_returncode = proc.returncode

    def _collect_consortium_logs(self) -> None:
        """Parse consortium JSONL sidecar logs with line annotation.

        Fix #11: annotate with consortium source file + 1-based line.
        """
        consortium_dir = self.workspace / ".pi" / "consortium"
        if consortium_dir.exists():
            logs = sorted(consortium_dir.glob("*.jsonl"))
            if len(logs) != 1:
                self.protocol_errors.append(f"Expected 1 consortium JSONL, found {len(logs)}")
            for log_file in logs:
                fname = log_file.name
                for line_num, line in enumerate(log_file.read_text().splitlines(), 1):
                    line = line.strip()
                    if line:
                        try:
                            ev = json.loads(line)
                            ev["_source_file"] = fname
                            ev["_source_line"] = line_num
                            self.consortium_events.append(ev)
                        except json.JSONDecodeError as exc:
                            self.protocol_errors.append(f"Invalid consortium JSONL {fname}:{line_num}: {exc}")

    def _collect_session_logs(self) -> None:
        """Parse session JSONL logs with line annotation."""
        if self.sessions_dir.exists():
            logs = sorted(self.sessions_dir.rglob("*.jsonl"))
            if len(logs) != 1:
                self.protocol_errors.append(f"Expected 1 session JSONL, found {len(logs)}")
            for log_file in logs:
                fname = log_file.name
                for line_num, line in enumerate(log_file.read_text().splitlines(), 1):
                    line = line.strip()
                    if line:
                        try:
                            ev = json.loads(line)
                            ev["_source_file"] = fname
                            ev["_source_line"] = line_num
                            self.session_events.append(ev)
                        except json.JSONDecodeError as exc:
                            self.protocol_errors.append(f"Invalid session JSONL {fname}:{line_num}: {exc}")

    def _validate_all(self) -> List[Assertion]:
        """Evaluate all frozen gates and retain complete metric objects."""
        all_events = self.rpc_events + self.session_events
        assertions: List[Assertion] = []

        rc = self.process_returncode if self.process_returncode is not None else -1
        assertions.append(validate_process_exit(rc))

        initial_state = self.responses.get("get_state", {}).get("data", {})
        final_state = self.responses.get("state_final", {}).get("data", {})
        for validator in (validate_provider_exact, validate_model_exact, validate_thinking_off):
            assertion = validator(initial_state)
            final_assertion = validator(final_state)
            if not final_assertion.passed:
                assertion.passed = False
                assertion.details += f"; final_state: {final_assertion.details}"
            assertion.evidence.append({"file": "rpc-events.jsonl", "line": 1, "states": ["get_state", "state_final"]})
            assertions.append(assertion)

        assertions.append(validate_prompts_count(self.outgoing_commands, self.responses))
        assertions.append(validate_response_success(self.responses))
        assertions.append(validate_commands_registered(self.responses.get("get_commands")))
        assertions.append(validate_no_extension_error(self.rpc_events))
        assertions.append(validate_protocol_clean(self.protocol_errors))
        assertions.append(validate_compaction(all_events))
        assertions.append(validate_confinement(self.rpc_events, self.workspace))
        assertions.append(validate_edit_recovery(self.rpc_events))
        assertions.append(validate_stage_a_cardinality(self.consortium_events))
        assertions.append(validate_usage_honesty(self.consortium_events))

        observed_prompt_count = len([c for c in self.outgoing_commands if c.get("type") == "prompt"])
        a_m6, m6_result = validate_m6(self.consortium_events, observed_prompt_count)
        a_m7a, m7a_result = validate_m7a(self.consortium_events, self.wall_clock_ms)
        a_m7b, m7b_result = validate_m7b(self.consortium_events)
        a_m8 = validate_m8(self.responses.get("stats_final"))
        assertions.extend([a_m6, a_m7a, a_m7b, a_m8])
        self.metric_results = {
            "m6": m6_result,
            "m7a": m7a_result,
            "m7b": m7b_result,
            "m8": (a_m8.evidence[0].get("tokens") if a_m8.evidence else None),
        }

        rn_path = self.workspace / "RELEASE_NOTES.txt"
        rn_contents = rn_path.read_text() if rn_path.exists() else ""
        assertions.append(validate_fixture(rn_contents))
        final_text = self.responses.get("text_final", {}).get("data", {}).get("text", "")
        assertions.append(validate_final_text(final_text))
        assertions.append(validate_path_diff(self.workspace, TEMPLATE_WORKSPACE))
        assertions.append(validate_manifest_identities(self.manifest))

        default_evidence = {
            "A01-process-exit": "manifest.json",
            "A05-prompts-count": "outgoing-commands.jsonl",
            "A06-response-success": "rpc-events.jsonl",
            "A07-commands-registered": "rpc-events.jsonl",
            "A08-no-extension-error": "rpc-events.jsonl",
            "A09-protocol-clean": "raw-incoming.jsonl",
            "A10-compaction": "rpc-events.jsonl",
            "A11-confinement": "rpc-events.jsonl",
            "A12-edit-recovery": "rpc-events.jsonl",
            "A13-stage-a-cardinality": "consortium/",
            "A14-usage-honesty": "consortium/",
            "A15-M6-injection-rate": "consortium/",
            "A16-M7a-latency": "consortium/",
            "A17-M7b-extraction": "consortium/",
            "A18-M8-tokens": "stats_final.json",
            "A19-fixture-marker": "fixture-after/RELEASE_NOTES.txt",
            "A20-final-text": "text_final.json",
            "A21-path-diff": "fixture-after.diff",
            "A22-frozen-identities": "manifest.json",
        }
        for assertion in assertions:
            if not assertion.evidence:
                assertion.evidence.append({
                    "file": default_evidence.get(assertion.assertion_id, "rpc-events.jsonl"),
                    "line": 1,
                })
        return assertions

    def _build_result(
        self,
        assertions: List[Assertion],
        manifest: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the final result dict with all computed objects persisted.

        Fix #11: Persist full M6/M7a/M7b/M8 in result/verdict evidence.
        """
        all_pass = all(a.passed for a in assertions)

        result = {
            "run_id": self.run_id,
            "repetition": self.repetition,
            "pass": all_pass,
            "process_returncode": self.process_returncode,
            "wall_clock_ms": round(self.wall_clock_ms, 1),
            "live_boundary_timestamp": self.live_boundary_ts,
            "prompts_delivered": len([c for c in self.outgoing_commands if c.get("type") == "prompt"]),
            "timeout_occurred": self.timeout_occurred,
            "exception": self.exception_info,
            "assertions": [a.to_dict() for a in assertions],
            "metrics": copy.deepcopy(self.metric_results),
            "manifest": manifest,
        }
        return result

    def _classify_exit_code(self, assertions: List[Assertion]) -> int:
        """Fix #15: Exit classification.

        2 for protocol/model/identity/compaction/confinement/extension/process infrastructure
        1 behavior/assertion failure
        0 all pass
        """
        if all(a.passed for a in assertions):
            return 0

        infra_ids = {
            "A01-process-exit", "A02-provider-exact", "A03-model-exact",
            "A04-thinking-off", "A05-prompts-count", "A06-response-success",
            "A07-commands-registered", "A08-no-extension-error",
            "A09-protocol-clean", "A10-compaction", "A11-confinement",
            "A22-frozen-identities",
        }
        for a in assertions:
            if not a.passed and a.assertion_id in infra_ids:
                return 2
        return 1

    def _harvest_evidence(
        self,
        result: Dict[str, Any],
        manifest: Dict[str, Any],
    ) -> None:
        """Harvest all evidence to .parcour-runs/<id>.

        Fix #14: harvest on assertion failure and infrastructure exception.
        Fix #11: every assertion has ≥1 evidence pointer.
        """
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # Manifest
        (self.evidence_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str) + "\n"
        )

        # P00 scenario metadata
        (self.evidence_dir / "p00-scenario-metadata.json").write_text(
            json.dumps(json.loads(TEMPLATE_META.read_text()), indent=2) + "\n"
        )

        # Fixture before
        fixture_before_dir = self.evidence_dir / "fixture-before"
        fixture_before_dir.mkdir(exist_ok=True)
        for src in TEMPLATE_WORKSPACE.rglob("*"):
            if src.is_file():
                dst = fixture_before_dir / src.relative_to(TEMPLATE_WORKSPACE)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))

        # Fixture after
        fixture_after_dir = self.evidence_dir / "fixture-after"
        fixture_after_dir.mkdir(exist_ok=True)
        if self.workspace.exists():
            for src in self.workspace.rglob("*"):
                if src.is_file() and not str(src).startswith(str(self.workspace / ".pi")):
                    dst = fixture_after_dir / src.relative_to(self.workspace)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))

        # Fixture diff
        rn_before = (TEMPLATE_WORKSPACE / "RELEASE_NOTES.txt").read_text()
        rn_after_path = self.workspace / "RELEASE_NOTES.txt"
        rn_after = rn_after_path.read_text() if rn_after_path.exists() else ""
        diff_lines = difflib.unified_diff(
            rn_before.splitlines(keepends=True),
            rn_after.splitlines(keepends=True),
            fromfile="RELEASE_NOTES.txt (before)",
            tofile="RELEASE_NOTES.txt (after)",
        )
        (self.evidence_dir / "fixture-after.diff").write_text("".join(diff_lines))

        boundary = self.tmp_root / "live-boundary.json"
        if boundary.exists():
            shutil.copy2(str(boundary), str(self.evidence_dir / "live-boundary.json"))

        # Raw incoming JSONL
        (self.evidence_dir / "raw-incoming.jsonl").write_text(
            "\n".join(self.raw_incoming) + ("\n" if self.raw_incoming else "")
        )

        # Outgoing commands and complete chronological two-direction RPC transcript.
        (self.evidence_dir / "outgoing-commands.jsonl").write_text(
            "\n".join(json.dumps(c) for c in self.outgoing_records) + ("\n" if self.outgoing_records else "")
        )
        (self.evidence_dir / "combined-directional.jsonl").write_text(
            "\n".join(json.dumps(d) for d in self.directional_records) + ("\n" if self.directional_records else "")
        )
        rpc_src = self.tmp_root / "rpc-events.jsonl"
        if rpc_src.exists():
            shutil.copy2(str(rpc_src), str(self.evidence_dir / "rpc-events.jsonl"))

        # Stderr
        (self.evidence_dir / "rpc-stderr.log").write_text(
            "\n".join(self.stderr_lines) + ("\n" if self.stderr_lines else "")
        )

        # Sessions
        sessions_dst = self.evidence_dir / "sessions"
        sessions_dst.mkdir(exist_ok=True)
        if self.sessions_dir.exists():
            for sf in self.sessions_dir.rglob("*.jsonl"):
                dst = sessions_dst / sf.relative_to(self.sessions_dir)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(sf), str(dst))

        # Consortium logs AND md sidecars
        consortium_dst = self.evidence_dir / "consortium"
        consortium_dst.mkdir(exist_ok=True)
        consortium_dir = self.workspace / ".pi" / "consortium"
        if consortium_dir.exists():
            for cf in sorted(consortium_dir.iterdir()):
                if cf.is_file():
                    shutil.copy2(str(cf), str(consortium_dst / cf.name))

        # Final state/entries/stats/text
        for key in ("state_final", "entries_final", "stats_final", "text_final"):
            resp = self.responses.get(key)
            if resp:
                (self.evidence_dir / f"{key}.json").write_text(
                    json.dumps(resp, indent=2, default=str) + "\n"
                )

        # Result and verdict
        (self.evidence_dir / "result.json").write_text(
            json.dumps(result, indent=2, default=str) + "\n"
        )
        verdict = result.get("assertions", [])
        (self.evidence_dir / "verdict.json").write_text(
            json.dumps(verdict, indent=2, default=str) + "\n"
        )

        # Source workspace
        source_ws = self.evidence_dir / "workspace"
        source_ws.mkdir(exist_ok=True)
        if self.workspace.exists():
            for src in self.workspace.rglob("*"):
                if src.is_file():
                    dst = source_ws / src.relative_to(self.workspace)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))

        # Evidence manifest (excludes itself)
        evidence_files: List[Dict[str, Any]] = []
        for ef in sorted(self.evidence_dir.rglob("*")):
            if ef.is_file() and ef.name != "evidence-manifest.json":
                evidence_files.append({
                    "path": str(ef.relative_to(self.evidence_dir)),
                    "sha256": sha256_file(ef),
                    "size": ef.stat().st_size,
                })
        em = {
            "run_id": self.run_id,
            "files": evidence_files,
            "coverage": {
                "total_files": len(evidence_files),
                "total_bytes": sum(f["size"] for f in evidence_files),
            },
        }
        (self.evidence_dir / "evidence-manifest.json").write_text(
            json.dumps(em, indent=2) + "\n"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. One run per invocation."""
    parser = argparse.ArgumentParser(description="Phase 0.5 behavioral parcour runner")
    parser.add_argument("--run-id", required=True, help="Unique safe run identifier")
    parser.add_argument(
        "--repetition", type=int, required=True, choices=[1, 2],
        help="Repetition number (1 or 2)",
    )
    args = parser.parse_args(argv)

    runner = Phase05Runner(
        run_id=args.run_id,
        repetition=args.repetition,
    )
    result = runner.run()

    print(json.dumps(result, indent=2, default=str))

    # Fix #15: exit classification
    assertions = result.get("assertions", [])
    if result.get("pass") is True:
        return 0
    if result.get("harvest_error"):
        return 2

    infra_ids = {
        "A01-process-exit", "A02-provider-exact", "A03-model-exact",
        "A04-thinking-off", "A05-prompts-count", "A06-response-success",
        "A07-commands-registered", "A08-no-extension-error",
        "A09-protocol-clean", "A10-compaction", "A11-confinement",
        "A22-frozen-identities",
    }
    for a in assertions:
        if not a["pass"] and a["id"] in infra_ids:
            return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())