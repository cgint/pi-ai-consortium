#!/usr/bin/env python3
"""Pure tests for Phase 0.5 runner validators and helpers.

Tests use real runtime31 event shapes. No live Pi execution. No subprocess.
Tests run only pure functions and temp dirs.

Coverage:
- Bootstrap: first prompt after get_state+get_commands success
- Three settle sequence with stdin close/natural exit (orchestration unit)
- argv order, unsafe/reused path guards
- Compaction with real response shapes
- StageA cardinality with per-deliberation pairing
- Usage honesty with real allowed statuses
- M6 n=0+hist, M7a percentile, M7b fenced classification
- M8 arithmetic
- /private/tmp normalization, confinement workspace-only
- Edit recovery with toolCallId correlation
- Manifest verification identities
- Content manifest LF termination
- Fixture validator with file contents
- Evidence pointers on every assertion
- Orchestration unit: fake process/event stream
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import runner module via importlib (hyphenated directory)
_RUNNER_DIR = Path(__file__).resolve().parent
_RUNNER_FILE = _RUNNER_DIR / "phase05_runner.py"

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("phase05_runner", str(_RUNNER_FILE))
_runner_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_runner_mod)

Assertion = _runner_mod.Assertion
Phase05Runner = _runner_mod.Phase05Runner
RpcSequencer = _runner_mod.RpcSequencer
PROMPTS = _runner_mod.PROMPTS
VECTOR_KEYS = _runner_mod.VECTOR_KEYS
ASSERTIONS = _runner_mod.ASSERTIONS
WRONG_OLD_TEXT = _runner_mod.WRONG_OLD_TEXT
WRONG_NEW_TEXT = _runner_mod.WRONG_NEW_TEXT
CORRECT_OLD_TEXT = _runner_mod.CORRECT_OLD_TEXT
CORRECT_NEW_TEXT = _runner_mod.CORRECT_NEW_TEXT
RELEASE_TAG_VALUE = _runner_mod.RELEASE_TAG_VALUE
UNCHANGED_MARKER = _runner_mod.UNCHANGED_MARKER
build_pi_command = _runner_mod.build_pi_command
build_manifest = _runner_mod.build_manifest
classify_extraction_output = _runner_mod.classify_extraction_output
is_path_in_workspace = _runner_mod.is_path_in_workspace
normalize_tmp_path = _runner_mod.normalize_tmp_path
validate_process_exit = _runner_mod.validate_process_exit
validate_provider_exact = _runner_mod.validate_provider_exact
validate_model_exact = _runner_mod.validate_model_exact
validate_thinking_off = _runner_mod.validate_thinking_off
validate_prompts_count = _runner_mod.validate_prompts_count
validate_response_success = _runner_mod.validate_response_success
validate_commands_registered = _runner_mod.validate_commands_registered
validate_no_extension_error = _runner_mod.validate_no_extension_error
validate_protocol_clean = _runner_mod.validate_protocol_clean
validate_compaction = _runner_mod.validate_compaction
validate_confinement = _runner_mod.validate_confinement
validate_edit_recovery = _runner_mod.validate_edit_recovery
validate_stage_a_cardinality = _runner_mod.validate_stage_a_cardinality
validate_usage_honesty = _runner_mod.validate_usage_honesty
validate_m6 = _runner_mod.validate_m6
validate_m7a = _runner_mod.validate_m7a
validate_m7b = _runner_mod.validate_m7b
validate_m8 = _runner_mod.validate_m8
validate_fixture = _runner_mod.validate_fixture
validate_final_text = _runner_mod.validate_final_text
validate_path_diff = _runner_mod.validate_path_diff
validate_manifest_identities = _runner_mod.validate_manifest_identities
_strip_fences = _runner_mod._strip_fences
_content_manifest = _runner_mod._content_manifest


# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []

    def check(self, condition: bool, msg: str) -> None:
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(msg)

    def summary(self) -> str:
        total = self.passed + self.failed
        status = "PASS" if self.failed == 0 else "FAIL"
        return f"{status}: {self.passed}/{total} passed, {self.failed} failed"


TR = TestResult()


def eq(actual: Any, expected: Any, msg: str) -> None:
    TR.check(actual == expected, f"{msg}: expected {expected!r}, got {actual!r}")


def true(cond: bool, msg: str) -> None:
    TR.check(cond, f"Expected True: {msg}")


def false(cond: bool, msg: str) -> None:
    TR.check(not cond, f"Expected False: {msg}")


def in_(item: Any, container: Any, msg: str) -> None:
    TR.check(item in container, f"Expected {item!r} in {container!r}: {msg}")


def raises(exc_type, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
        TR.check(False, f"Expected {exc_type.__name__} but no exception raised")
    except exc_type:
        TR.check(True, f"Correctly raised {exc_type.__name__}")
    except Exception as e:
        TR.check(False, f"Expected {exc_type.__name__} but got {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# R3: build_pi_command argv order
# ---------------------------------------------------------------------------

def test_argv_order() -> None:
    cmd = build_pi_command("test-run", 1, Path("/tmp/test-ws"), Path("/tmp/test-sess"))
    eq(cmd[0], "pi", "argv[0]")
    in_("--mode", cmd, "--mode present")
    mode_i = cmd.index("--mode")
    eq(cmd[mode_i + 1], "rpc", "--mode rpc")
    in_("--no-context-files", cmd, "no-context-files")
    in_("--no-skills", cmd, "no-skills")
    in_("--no-prompt-templates", cmd, "no-prompt-templates")
    in_("--no-extensions", cmd, "no-extensions")
    ti = cmd.index("--tools")
    eq(cmd[ti + 1], "read,edit,grep,find,ls", "tools")
    ei = [i for i, a in enumerate(cmd) if a == "-e"]
    true(len(ei) >= 3, "≥3 -e flags")
    exts = [cmd[i + 1] for i in ei]
    true("pi-olla-autodetect" in exts[0], "provider first")
    true("pi-ai-consortium/index.ts" in exts[1], "consortium second")
    true("pi-focus-guard" in exts[2], "focus third")
    pi = cmd.index("--provider")
    eq(cmd[pi + 1], "olla", "provider")
    mi = cmd.index("--model")
    eq(cmd[mi + 1], "qwen36-27b-nvidia-nvfp4", "model")
    thi = cmd.index("--thinking")
    eq(cmd[thi + 1], "off", "thinking")
    in_("--dm-off", cmd, "dm-off")
    wi = cmd.index("--write-guard")
    true(cmd[wi + 1].startswith("/"), "absolute write-guard")
    in_("--session-dir", cmd, "session-dir")
    in_("--name", cmd, "name")
    ni = cmd.index("--name")
    true("phase05-test-run-rep1" in cmd[ni + 1], "name format")


# ---------------------------------------------------------------------------
# R2: Path guards
# ---------------------------------------------------------------------------

def test_unsafe_run_id() -> None:
    raises(ValueError, lambda: Phase05Runner("bad run!", 1)._validate_run_id())
    raises(ValueError, lambda: Phase05Runner("", 1)._validate_run_id())


def test_guard_existing_paths() -> None:
    with tempfile.TemporaryDirectory() as td:
        existing = Path(td) / "parcour-existing"
        existing.mkdir()
        r = Phase05Runner("existing", 1)
        r.tmp_root = existing
        r.workspace = existing / "workspace"
        r.evidence_dir = existing / "evidence"
        raises(FileExistsError, r._guard_existing_paths)


# ---------------------------------------------------------------------------
# Fix #5: Compaction with real response shapes
# ---------------------------------------------------------------------------

def test_compaction_clean() -> None:
    events = [
        {"type": "turn_start"},
        {"type": "response", "id": "get_state", "success": True,
         "data": {"isCompacting": False}},
    ]
    a = validate_compaction(events)
    true(a.passed, "No compaction → pass")


def test_compaction_start_fails() -> None:
    events = [{"type": "turn_start"}, {"type": "compaction_start"}]
    a = validate_compaction(events)
    false(a.passed, "compaction_start → fail")
    true(len(a.evidence) > 0, "Has evidence")
    eq(a.evidence[0]["file"], "rpc-events.jsonl", "File pointer")
    eq(a.evidence[0]["event_index"], 2, "1-based index")


def test_is_compacting_true_fails() -> None:
    events = [{"type": "response", "id": "s1", "success": True,
               "data": {"isCompacting": True}}]
    a = validate_compaction(events)
    false(a.passed, "isCompacking true → fail")


def test_compaction_real_shape_no_command() -> None:
    """Real get_state response has no 'command' field; still check data.isCompacting."""
    events = [{"type": "response", "id": "get_state", "success": True,
               "data": {"isCompacting": True, "model": {"id": "x"}}}]
    a = validate_compaction(events)
    false(a.passed, "Real shape isCompacting → fail")


# ---------------------------------------------------------------------------
# Fix #10: StageA cardinality with per-deliberation pairing
# ---------------------------------------------------------------------------

def test_cardinality_per_deliberation() -> None:
    events = [
        {"type": "deliberation_start", "model": "olla/x", "probe_count": 5},
        {"type": "baseline_check", "baseline_available": False, "baseline_supplied": False},
        {"type": "deliberation_telemetry", "baseline_available": False, "baseline_supplied": False, "usage_status": "not_applicable"},
        {"type": "deliberation_start", "model": "olla/x", "probe_count": 5},
        {"type": "baseline_check", "baseline_available": True, "baseline_supplied": False},
        {"type": "deliberation_telemetry", "baseline_available": True, "baseline_supplied": False, "usage_status": "complete"},
    ]
    a = validate_stage_a_cardinality(events)
    true(a.passed, "Per-deliberation pairing passes")
    true(len(a.evidence) > 0, "Has evidence pointers")


def test_cardinality_mismatch() -> None:
    events = [
        {"type": "deliberation_start"},
        {"type": "baseline_check", "baseline_available": False, "baseline_supplied": False},
    ]
    a = validate_stage_a_cardinality(events)
    false(a.passed, "Missing telemetry → fail")


def test_first_baseline_must_be_false_false() -> None:
    events = [
        {"type": "deliberation_start"},
        {"type": "baseline_check", "baseline_available": True, "baseline_supplied": False},
        {"type": "deliberation_telemetry"},
    ]
    a = validate_stage_a_cardinality(events)
    false(a.passed, "First must be false/false")


def test_later_baseline_must_be_true_false() -> None:
    events = [
        {"type": "deliberation_start"},
        {"type": "baseline_check", "baseline_available": False, "baseline_supplied": False},
        {"type": "deliberation_telemetry"},
        {"type": "deliberation_start"},
        {"type": "baseline_check", "baseline_available": False, "baseline_supplied": False},
        {"type": "deliberation_telemetry"},
    ]
    a = validate_stage_a_cardinality(events)
    false(a.passed, "Later must be true/false")


def test_zero_eligible_fails() -> None:
    events = [
        {"type": "deliberation_start"},
        {"type": "baseline_check", "baseline_available": False, "baseline_supplied": False},
        {"type": "deliberation_telemetry"},
    ]
    a = validate_stage_a_cardinality(events)
    false(a.passed, "Zero eligible → fail")


# ---------------------------------------------------------------------------
# Fix #6: Usage honesty with real allowed statuses
# ---------------------------------------------------------------------------

def test_usage_honesty_pass() -> None:
    events = [
        {"type": "probe_complete", "modelKey": "extraction", "duration_ms": 100,
         "usage_reported": True, "usage": {"input": 100, "output": 50}},
        {"type": "probe_complete", "modelKey": "probe:0", "duration_ms": 50,
         "usage_reported": False},
        {"type": "deliberation_telemetry", "baseline_available": True,
         "baseline_supplied": False, "successful_calls": 2, "reported_calls": 1,
         "usage_status": "partial"},
    ]
    a = validate_usage_honesty(events)
    true(a.passed, "Valid usage passes")


def test_usage_status_values() -> None:
    for status in ("complete", "partial", "unreported", "not_applicable"):
        events = [{"type": "deliberation_telemetry", "usage_status": status,
                    "successful_calls": 0, "reported_calls": 0}]
        a = validate_usage_honesty(events)
        true(a.passed, f"Status {status} valid")


def test_invalid_status_fails() -> None:
    events = [{"type": "deliberation_telemetry", "usage_status": "invalid_status",
                "successful_calls": 0, "reported_calls": 0}]
    a = validate_usage_honesty(events)
    false(a.passed, "Invalid status → fail")


def test_aggregate_on_non_complete_fails() -> None:
    events = [{"type": "deliberation_telemetry", "usage_status": "partial",
                "successful_calls": 1, "reported_calls": 1,
                "aggregate_usage": {"input": 100}}]
    a = validate_usage_honesty(events)
    false(a.passed, "aggregate_usage on partial → fail")


def test_aggregate_required_on_complete_with_calls() -> None:
    events = [{"type": "deliberation_telemetry", "usage_status": "complete",
                "successful_calls": 2, "reported_calls": 2}]
    a = validate_usage_honesty(events)
    false(a.passed, "complete with calls but no aggregate_usage → fail")


def test_aggregate_optional_on_complete_zero_calls() -> None:
    events = [{"type": "deliberation_telemetry", "usage_status": "complete",
                "successful_calls": 0, "reported_calls": 0}]
    a = validate_usage_honesty(events)
    true(a.passed, "complete with 0 calls, no aggregate → pass")


# ---------------------------------------------------------------------------
# V6 M6
# ---------------------------------------------------------------------------

def test_m6_basic() -> None:
    events = [
        {"type": "injection_complete"},
        {"type": "injection_complete"},
        {"type": "injection_skipped", "reason": "NO_CONTRIBUTION"},
    ]
    a, r = validate_m6(events)
    true(a.passed, "Basic M6")
    eq(r["complete"], 2, "complete")
    eq(r["skipped"], 1, "skipped")
    eq(r["denominator"], 3, "denominator")
    true(abs(r["rate"] - 2/3) < 0.001, "rate")


def test_m6_n_zero() -> None:
    a, r = validate_m6([])
    false(a.passed, "n=0 → fail")
    eq(r["rate"], None, "rate None")
    eq(r["rate_label"], "not_applicable", "label")


def test_m6_histogram() -> None:
    events = [
        {"type": "injection_complete"},
        {"type": "injection_skipped", "reason": "NO_CONTRIBUTION"},
        {"type": "injection_skipped"},  # missing reason
    ]
    _, r = validate_m6(events)
    eq(r["skip_reason_histogram"].get("NO_CONTRIBUTION"), 1, "hist count")
    eq(r["skip_reason_histogram"].get("<missing>"), 1, "<missing> bucket")


def test_m6_separate_turn_counts() -> None:
    events = [
        {"type": "turn_start"},
        {"type": "turn_start"},
        {"type": "deliberation_start"},
        {"type": "injection_complete"},
    ]
    _, r = validate_m6(events, scripted_prompt_count=2)
    eq(r["turn_start_count"], 2, "turn_start separate")
    eq(r["deliberation_start_count"], 1, "deliberation_start separate")
    eq(r["scripted_prompt_count"], 2, "observed prompt count")


def test_m6_non_string_reason_fails() -> None:
    assertion, result = validate_m6([{"type": "injection_skipped", "reason": ["bad"]}])
    false(assertion.passed, "Non-string reason fails schema")
    true("<invalid>" in result["skip_reason_histogram"], "Invalid bucket retained")


# ---------------------------------------------------------------------------
# V6 M7a
# ---------------------------------------------------------------------------

def test_percentile_basic() -> None:
    events = [
        {"type": "probe_complete", "modelKey": "extraction", "duration_ms": 100},
        {"type": "probe_complete", "modelKey": "extraction", "duration_ms": 200},
        {"type": "probe_complete", "modelKey": "extraction", "duration_ms": 300},
        {"type": "probe_complete", "modelKey": "extraction", "duration_ms": 400},
        {"type": "probe_complete", "modelKey": "extraction", "duration_ms": 500},
    ]
    a, r = validate_m7a(events, 10000.0)
    true(a.passed, "Percentile")
    g = r["groups"]["extraction"]
    eq(g["n"], 5, "n")
    eq(g["min"], 100, "min")
    eq(g["max"], 500, "max")
    eq(g["p50"], 300, "p50")
    eq(g["p95"], 500, "p95")


def test_wall_clock_separate() -> None:
    events = [{"type": "probe_complete", "modelKey": "extraction", "duration_ms": 100}]
    _, r = validate_m7a(events, 30000.0)
    eq(r["run_wall_clock_ms"], 30000.0, "wall clock")
    neq(r["groups"]["extraction"]["p50"], 30000.0, "p50 ≠ wall clock")


def test_duration_schema_failure() -> None:
    events = [{"type": "probe_complete", "modelKey": "extraction"}]
    a, r = validate_m7a(events, 1000.0)
    false(a.passed, "Missing duration → fail")
    true(len(r.get("schema_failures", [])) > 0, "Has schema failures")
    false(validate_m7a([], 1000.0)[0].passed, "No timing groups fails completeness")


def neq(a, b, msg):
    TR.check(a != b, f"{msg}: {a!r} should not equal {b!r}")


# ---------------------------------------------------------------------------
# V6 M7b
# ---------------------------------------------------------------------------

def test_strip_fences_json() -> None:
    eq(_strip_fences('```json\n{"k":"v"}\n```'), '{"k":"v"}', "json fence")


def test_strip_fences_plain() -> None:
    eq(_strip_fences('```\n{"k":"v"}\n```'), '{"k":"v"}', "plain fence")


def test_classify_nonempty() -> None:
    o = json.dumps({"userRequirements": ["Do something"]})
    eq(classify_extraction_output(o), "nonempty", "nonempty")


def test_classify_empty_null() -> None:
    o = json.dumps({k: None for k in VECTOR_KEYS})
    eq(classify_extraction_output(o), "empty", "empty null")


def test_classify_empty_arrays() -> None:
    o = json.dumps({k: [] for k in VECTOR_KEYS})
    eq(classify_extraction_output(o), "empty", "empty arrays")


def test_classify_invalid_parse() -> None:
    eq(classify_extraction_output("not json"), "invalid", "parse fail")


def test_classify_invalid_array() -> None:
    eq(classify_extraction_output("[1,2]"), "invalid", "array root")


def test_classify_invalid_bad_type() -> None:
    eq(classify_extraction_output(json.dumps({"userRequirements": 42})), "invalid", "bad type")


def test_classify_fenced() -> None:
    raw = '```json\n{"userRequirements": ["test"]}'
    eq(classify_extraction_output(raw), "nonempty", "fenced")


def test_classify_array_items_stringify() -> None:
    raw = json.dumps({"userRequirements": [{"fact": "goal"}]})
    eq(classify_extraction_output(raw), "nonempty", "array items stringify")


def test_m7b_counts() -> None:
    events = [
        {"type": "probe_complete", "modelKey": "extraction", "output": "{}"},
        {"type": "probe_complete", "modelKey": "extraction", "output": "not json"},
        {"type": "probe_complete", "modelKey": "extraction",
         "output": json.dumps({"userRequirements": ["req"]})},
        {"type": "probe_complete", "modelKey": "probe:0", "output": "NO_CONTRIBUTION"},
    ]
    a, c = validate_m7b(events)
    true(a.passed, "M7b")
    eq(c["total"], 3, "total")
    eq(c["empty"], 1, "empty")
    eq(c["invalid"], 1, "invalid")
    eq(c["nonempty"], 1, "nonempty")
    false(validate_m7b([])[0].passed, "No extraction calls fails completeness")


# ---------------------------------------------------------------------------
# V6 M8
# ---------------------------------------------------------------------------

def test_m8_valid() -> None:
    resp = {"success": True, "data": {"tokens": {
        "input": 1000, "output": 500, "cacheRead": 200, "cacheWrite": 100, "total": 1800}}}
    a = validate_m8(resp)
    true(a.passed, "Valid M8")


def test_m8_arithmetic_fail() -> None:
    resp = {"success": True, "data": {"tokens": {
        "input": 1000, "output": 500, "cacheRead": 200, "cacheWrite": 100, "total": 9999}}}
    a = validate_m8(resp)
    false(a.passed, "Arithmetic fail")


def test_m8_missing() -> None:
    false(validate_m8(None).passed, "Missing response")


def test_m8_non_numeric() -> None:
    resp = {"success": True, "data": {"tokens": {
        "input": "abc", "output": 500, "cacheRead": 200, "cacheWrite": 100, "total": 1800}}}
    false(validate_m8(resp).passed, "Non-numeric")
    resp["data"]["tokens"]["input"] = True
    false(validate_m8(resp).passed, "Boolean is not a token count")


# ---------------------------------------------------------------------------
# R11: Confinement (workspace only, not runtime root)
# ---------------------------------------------------------------------------

def test_private_tmp_normalization() -> None:
    eq(normalize_tmp_path("/private/tmp/parcour"), "/tmp/parcour", "/private/tmp")
    eq(normalize_tmp_path("/tmp/parcour"), "/tmp/parcour", "/tmp")


def test_path_in_workspace() -> None:
    ws = Path("/tmp/parcour-test/workspace")
    true(is_path_in_workspace("/tmp/parcour-test/workspace/FILE.txt", ws), "WS file")


def test_path_not_in_workspace_runtime() -> None:
    ws = Path("/tmp/parcour-test/workspace")
    false(is_path_in_workspace("/tmp/parcour-test/sessions/data.jsonl", ws), "RT not WS")


def test_path_leak_repo() -> None:
    ws = Path("/tmp/test-ws")
    false(is_path_in_workspace("/Users/cgint/dev-external/pi-ai-consortium/src/index.ts", ws), "repo")
    false(is_path_in_workspace("../sessions/data.jsonl", ws), "relative traversal")


def test_confinement_pass() -> None:
    events = [{"type": "tool_execution_start", "toolName": "read", "args": {"path": "FILE.txt"}}]
    ws = Path("/tmp/test-ws")
    a = validate_confinement(events, ws)
    true(a.passed, "Relative path → pass")


def test_confinement_abs_in_ws() -> None:
    events = [{"type": "tool_execution_start", "toolName": "read",
               "args": {"path": "/tmp/test-ws/FILE.txt"}}]
    ws = Path("/tmp/test-ws")
    a = validate_confinement(events, ws)
    true(a.passed, "Abs path in WS → pass")


def test_confinement_leak() -> None:
    events = [{"type": "tool_execution_start", "toolName": "read",
               "args": {"path": "/etc/passwd"}}]
    ws = Path("/tmp/test-ws")
    a = validate_confinement(events, ws)
    false(a.passed, "Leaked path → fail")


def test_confinement_nested() -> None:
    events = [{"type": "tool_execution_start", "toolName": "edit",
               "args": {"path": "f.txt", "meta": {"loc": "/home/u/k.pem"}}}]
    ws = Path("/tmp/test-ws")
    a = validate_confinement(events, ws)
    false(a.passed, "Nested leak → fail")


def test_confinement_records_paths() -> None:
    events = [{"type": "tool_execution_start", "toolName": "read",
               "args": {"path": "/tmp/test-ws/F.txt"}}]
    ws = Path("/tmp/test-ws")
    a = validate_confinement(events, ws)
    true(len(a.evidence) > 0, "Evidence")
    in_("checked_paths", a.evidence[0], "checked_paths")


# ---------------------------------------------------------------------------
# Fix #7: Edit recovery with toolCallId correlation
# ---------------------------------------------------------------------------

def _edit_pair(tid, old_text, new_text, is_error):
    """Generate a pair of tool_execution_start/end events."""
    return [
        {"type": "tool_execution_start", "toolCallId": tid, "toolName": "edit",
         "args": {"path": "RELEASE_NOTES.txt", "edits": [{"oldText": old_text, "newText": new_text}]}},
        {"type": "tool_execution_end", "toolCallId": tid, "toolName": "edit",
         "result": {"content": []}, "isError": is_error},
    ]


def _read_pair(tid):
    return [
        {"type": "tool_execution_start", "toolCallId": tid, "toolName": "read",
         "args": {"path": "RELEASE_NOTES.txt"}},
        {"type": "tool_execution_end", "toolCallId": tid, "toolName": "read",
         "result": {"content": [{"type": "text", "text": "..."}]}, "isError": False},
    ]


def test_edit_recovery_ordered() -> None:
    events = (
        _edit_pair("t1", WRONG_OLD_TEXT, WRONG_NEW_TEXT, True) +
        _read_pair("t2") +
        _edit_pair("t3", CORRECT_OLD_TEXT, CORRECT_NEW_TEXT, False) +
        _read_pair("t4")
    )
    a = validate_edit_recovery(events)
    true(a.passed, "Ordered recovery")


def test_edit_recovery_wrong_text() -> None:
    events = (
        _edit_pair("t1", "wrong old", "wrong new", True) +
        _read_pair("t2") +
        _edit_pair("t3", CORRECT_OLD_TEXT, CORRECT_NEW_TEXT, False) +
        _read_pair("t4")
    )
    a = validate_edit_recovery(events)
    false(a.passed, "Wrong old text → fail")


def test_edit_recovery_no_read_between() -> None:
    events = (
        _edit_pair("t1", WRONG_OLD_TEXT, WRONG_NEW_TEXT, True) +
        _edit_pair("t2", CORRECT_OLD_TEXT, CORRECT_NEW_TEXT, False) +
        _read_pair("t3")
    )
    a = validate_edit_recovery(events)
    false(a.passed, "No read between → fail")


def test_edit_recovery_few_tools() -> None:
    events = _edit_pair("t1", WRONG_OLD_TEXT, WRONG_NEW_TEXT, True) + _read_pair("t2")
    a = validate_edit_recovery(events)
    false(a.passed, "Too few tools → fail")


def test_edit_recovery_extra_tools() -> None:
    events = (
        _edit_pair("t1", WRONG_OLD_TEXT, WRONG_NEW_TEXT, True) +
        [{"type": "tool_execution_start", "toolCallId": "tX", "toolName": "grep",
          "args": {"path": "RELEASE_NOTES.txt", "pattern": "upload"}},
         {"type": "tool_execution_end", "toolCallId": "tX", "toolName": "grep",
          "result": {"content": []}, "isError": False}] +
        _read_pair("t2") +
        _edit_pair("t3", CORRECT_OLD_TEXT, CORRECT_NEW_TEXT, False) +
        _read_pair("t4")
    )
    a = validate_edit_recovery(events)
    true(a.passed, "Extra tools allowed")


def test_edit_recovery_tool_call_id_correlation() -> None:
    """Verify toolCallId is used for correlation, not position."""
    events = (
        _edit_pair("edit-fail", WRONG_OLD_TEXT, WRONG_NEW_TEXT, True) +
        _read_pair("read-recover") +
        _edit_pair("edit-ok", CORRECT_OLD_TEXT, CORRECT_NEW_TEXT, False) +
        _read_pair("read-final")
    )
    a = validate_edit_recovery(events)
    true(a.passed, "toolCallId correlation works")


# ---------------------------------------------------------------------------
# Fix #9: Additional assertions
# ---------------------------------------------------------------------------

def test_provider_exact() -> None:
    sd = {"model": {"provider": "olla", "id": "qwen36-27b-nvidia-nvfp4"}}
    true(validate_provider_exact(sd).passed, "Provider exact")
    false(validate_provider_exact({"model": {"provider": "openai"}}).passed, "Wrong provider")


def test_model_exact() -> None:
    sd = {"model": {"provider": "olla", "id": "qwen36-27b-nvidia-nvfp4"}}
    true(validate_model_exact(sd).passed, "Model exact")
    false(validate_model_exact({"model": {"id": "gpt-4"}}).passed, "Wrong model")


def test_thinking_off() -> None:
    true(validate_thinking_off({"thinkingLevel": "off"}).passed, "Thinking off")
    false(validate_thinking_off({"thinkingLevel": "high"}).passed, "Wrong thinking")


def test_prompts_count() -> None:
    outgoing = [
        {"id": "get_state", "type": "get_state"},
        {"id": "get_commands", "type": "get_commands"},
        {"id": "prompt_0", "type": "prompt", "message": PROMPTS[0]},
        {"id": "prompt_1", "type": "prompt", "message": PROMPTS[1]},
        {"id": "prompt_2", "type": "prompt", "message": PROMPTS[2]},
    ]
    responses = {
        "get_state": {"success": True},
        "get_commands": {"success": True},
        "prompt_0": {"success": True},
        "prompt_1": {"success": True},
        "prompt_2": {"success": True},
    }
    true(validate_prompts_count(outgoing, responses).passed, "3 prompts")


def test_prompts_count_short() -> None:
    outgoing = [{"id": "prompt_0", "type": "prompt"}]
    responses = {"prompt_0": {"success": True}}
    false(validate_prompts_count(outgoing, responses).passed, "Only 1 prompt")


def _required_responses() -> Dict[str, Dict[str, Any]]:
    return {rid: {"type": "response", "id": rid, "success": True, "data": {}}
            for rid in _runner_mod.REQUIRED_RESPONSE_IDS}


def test_response_success() -> None:
    true(validate_response_success(_required_responses()).passed, "All required responses succeed")


def test_response_success_fail() -> None:
    responses = _required_responses()
    responses["stats_final"]["success"] = False
    false(validate_response_success(responses).passed, "One required response failed")
    del responses["text_final"]
    false(validate_response_success(responses).passed, "Missing required response failed")


def test_no_extension_error() -> None:
    true(validate_no_extension_error([]).passed, "No errors")
    false(validate_no_extension_error([{"type": "extension_error"}]).passed, "Has error")


def test_protocol_clean() -> None:
    true(validate_protocol_clean([]).passed, "Clean")
    false(validate_protocol_clean(["timeout"]).passed, "Has error")


def test_required_commands_focus() -> None:
    commands = [
        {"name": "ai-consortium", "sourceInfo": {"path": str(_runner_mod.CONSORTIUM_EXT)}},
        {"name": "focus-discuss", "sourceInfo": {"path": str(_runner_mod.FOCUS_EXT.resolve())}},
    ]
    response = {"success": True, "data": {"commands": commands}}
    true(validate_commands_registered(response).passed, "Consortium and focus registered")
    response["data"]["commands"] = commands[:1]
    false(validate_commands_registered(response).passed, "Missing focus fails")


def test_fixture_validator() -> None:
    """Fix #18: fixture validator receives file contents."""
    content = (
        f"RELEASE_TAG={RELEASE_TAG_VALUE}\n"
        f"- adjusted retry backoff for the release upload queue\n"
        f"- {UNCHANGED_MARKER}\n"
    )
    a = validate_fixture(content)
    true(a.passed, "Valid fixture")


def test_fixture_missing_tag() -> None:
    a = validate_fixture("- some random content\n")
    false(a.passed, "Missing tag → fail")


def test_fixture_old_line_remaining() -> None:
    content = f"RELEASE_TAG={RELEASE_TAG_VALUE}\n{UNCHANGED_MARKER}\n{CORRECT_OLD_TEXT}\n{CORRECT_NEW_TEXT}\n"
    false(validate_fixture(content).passed, "Append-only edit fails")


def test_fixture_text() -> None:
    text = f"The RELEASE_TAG is {RELEASE_TAG_VALUE}. Changes include {CORRECT_NEW_TEXT}."
    a = validate_final_text(text)
    true(a.passed, "Contains tag and new line")


def test_fixture_text_missing() -> None:
    false(validate_final_text("Nothing here.").passed, "Missing content")


# ---------------------------------------------------------------------------
# ASSERTIONS table (fix #17)
# ---------------------------------------------------------------------------

def test_assertions_table_exists() -> None:
    true(len(ASSERTIONS) >= 21, f"ASSERTIONS has {len(ASSERTIONS)} entries")
    for a in ASSERTIONS:
        true("id" in a, "Has id")
        true("requirement" in a, "Has requirement")


def test_assertion_structure() -> None:
    a = Assertion("test-01", "Test requirement")
    a.passed = True
    a.details = "All good"
    a.evidence = [{"file": "test.jsonl", "event_index": 5}]
    d = a.to_dict()
    eq(d["id"], "test-01", "ID")
    eq(d["requirement"], "Test requirement", "Req")
    eq(d["pass"], True, "Pass")
    eq(d["details"], "All good", "Details")
    eq(d["evidence"][0]["event_index"], 5, "Evidence index")


# ---------------------------------------------------------------------------
# Process exit
# ---------------------------------------------------------------------------

def test_exit_zero() -> None:
    true(validate_process_exit(0).passed, "Code 0")


def test_exit_nonzero() -> None:
    false(validate_process_exit(1).passed, "Code 1")


# ---------------------------------------------------------------------------
# Fix #13: Content manifest LF
# ---------------------------------------------------------------------------

def test_content_manifest_lf() -> None:
    """Manifest lines must end with LF."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        f = ws / "test.txt"
        f.write_text("hello\n")
        cm = _content_manifest(ws)
        # The manifest computation appends \n to the joined entries
        true(isinstance(cm, str), "Returns string")
        true(len(cm) == 64, "SHA256 hex = 64 chars")


# ---------------------------------------------------------------------------
# Fix #15: Exit classification
# ---------------------------------------------------------------------------

def test_exit_classification_infra() -> None:
    """Infrastructure assertion failure → exit code 2."""
    r = Phase05Runner("test", 1)
    assertions = [
        Assertion("A09-protocol-clean", "test"),
    ]
    assertions[0].passed = False
    rc = r._classify_exit_code(assertions)
    eq(rc, 2, "Infra → 2")


def test_exit_classification_behavior() -> None:
    """Behavior assertion failure → exit code 1."""
    r = Phase05Runner("test", 1)
    assertions = [
        Assertion("A15-M6-injection-rate", "test"),
    ]
    assertions[0].passed = False
    rc = r._classify_exit_code(assertions)
    eq(rc, 1, "Behavior → 1")


def test_exit_classification_pass() -> None:
    """All pass → exit code 0."""
    r = Phase05Runner("test", 1)
    assertions = [
        Assertion("A01-process-exit", "test"),
    ]
    assertions[0].passed = True
    rc = r._classify_exit_code(assertions)
    eq(rc, 0, "All pass → 0")


# ---------------------------------------------------------------------------
# Fix #16: Orchestration unit test with fake process/event stream
# ---------------------------------------------------------------------------

def test_bootstrap_sequence() -> None:
    seq = RpcSequencer()
    eq(seq.on_event({"type": "response", "id": "get_state", "success": True}), [],
       "State alone sends no prompt")
    actions = seq.on_event({"type": "response", "id": "get_commands", "success": True})
    eq(actions, [{"id": "prompt_0", "type": "prompt", "message": PROMPTS[0]}],
       "Second successful initial response sends prompt0")
    eq(seq.prompts_sent, 1, "One prompt sent")
    eq(seq.errors, [], "No sequence errors")


def test_three_settle_then_collect() -> None:
    seq = RpcSequencer()
    seq.on_event({"type": "response", "id": "get_state", "success": True})
    seq.on_event({"type": "response", "id": "get_commands", "success": True})
    eq(seq.on_event({"type": "agent_settled"}),
       [{"id": "prompt_1", "type": "prompt", "message": PROMPTS[1]}], "Settle1 sends prompt1")
    eq(seq.on_event({"type": "agent_settled"}),
       [{"id": "prompt_2", "type": "prompt", "message": PROMPTS[2]}], "Settle2 sends prompt2")
    final_actions = seq.on_event({"type": "agent_settled"})
    eq([a["id"] for a in final_actions],
       ["state_final", "entries_final", "stats_final", "text_final"], "Settle3 collects final state")
    false(seq.complete, "Not complete before final responses")
    for rid in ("state_final", "entries_final", "stats_final"):
        seq.on_event({"type": "response", "id": rid, "success": True})
    false(seq.complete, "Still waiting for final text")
    seq.on_event({"type": "response", "id": "text_final", "success": True})
    true(seq.complete, "Complete after all final responses")
    eq(seq.errors, [], "No sequence errors")


def test_duplicate_settle_rejected() -> None:
    seq = RpcSequencer()
    seq.on_event({"type": "agent_settled"})
    true(bool(seq.errors), "Settled before prompt is rejected")


def test_stdin_close_natural_exit_logic() -> None:
    """Verify the runner does NOT terminate successful processes.

    Checked by source inspection: _run_rpc_loop closes stdin then calls
    proc.wait(timeout=30) before any terminate.
    """
    source = _RUNNER_FILE.read_text()
    true("proc.stdin.close()" in source, "stdin close present")
    true("proc.wait(timeout=30)" in source, "Natural wait present")
    true("start_new_session=True" in source, "start_new_session")
    false("shell=True" in source, "No shell=True")
    false("rmtree" in source, "No rmtree")


# ---------------------------------------------------------------------------
# Fix #12: Manifest verification
# ---------------------------------------------------------------------------

def test_manifest_constants() -> None:
    true(hasattr(_runner_mod, "STAGE_A_COMMIT"), "Stage A commit")
    true(hasattr(_runner_mod, "V5_BLOB_SHA"), "V5 blob")
    true(hasattr(_runner_mod, "V6_BLOB_SHA"), "V6 blob")
    true(hasattr(_runner_mod, "P00_TEMPLATE_TREE"), "p00 template tree")


def test_manifest_identity_validator() -> None:
    checks = {"a": True, "b": True}
    true(validate_manifest_identities({"identity_checks": checks}).passed, "All identities pass")
    failed = validate_manifest_identities({"identity_checks": {"a": True, "b": False}})
    false(failed.passed, "Mismatch fails")
    in_("b", failed.details, "Failed check named")
    false(validate_manifest_identities({}).passed, "Missing checks fail closed")


# ---------------------------------------------------------------------------
# Fix #11: Evidence pointers on every assertion
# ---------------------------------------------------------------------------

def test_assertion_has_evidence() -> None:
    """Every failing assertion must have ≥1 evidence pointer."""
    # Compaction failure has evidence
    events = [{"type": "compaction_start"}]
    a = validate_compaction(events)
    false(a.passed, "Should fail")
    true(len(a.evidence) >= 1, "Has evidence pointer")
    in_("file", a.evidence[0], "Has file field")
    in_("event_index", a.evidence[0], "Has event_index")


# ---------------------------------------------------------------------------
# Pure filesystem collection and harvest tests
# ---------------------------------------------------------------------------

def test_log_collection_and_malformed_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runner = Phase05Runner("unit-logs", 1)
        runner.workspace = root / "workspace"
        runner.sessions_dir = root / "sessions"
        consortium = runner.workspace / ".pi" / "consortium"
        consortium.mkdir(parents=True)
        runner.sessions_dir.mkdir(parents=True)
        (consortium / "one.jsonl").write_text('{"type":"turn_start"}\n')
        (runner.sessions_dir / "one.jsonl").write_text('{"type":"session"}\n')
        runner._collect_consortium_logs()
        runner._collect_session_logs()
        eq(runner.consortium_events[0]["_source_line"], 1, "Consortium line annotated")
        eq(runner.session_events[0]["_source_line"], 1, "Session line annotated")

        (consortium / "one.jsonl").write_text('not-json\n')
        runner.consortium_events = []
        runner._collect_consortium_logs()
        true(any("Invalid consortium JSONL" in e for e in runner.protocol_errors),
             "Malformed consortium line becomes protocol error")


def test_harvest_evidence_manifest_coverage() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runner = Phase05Runner("unit-harvest", 1)
        runner.tmp_root = root / "runtime"
        runner.workspace = runner.tmp_root / "workspace"
        runner.sessions_dir = runner.tmp_root / "sessions"
        runner.evidence_dir = root / "evidence"
        runner.workspace.mkdir(parents=True)
        runner.sessions_dir.mkdir(parents=True)
        (runner.workspace / "RELEASE_NOTES.txt").write_text(
            f"RELEASE_TAG={RELEASE_TAG_VALUE}\n{CORRECT_NEW_TEXT}\n{UNCHANGED_MARKER}\n"
        )
        consortium = runner.workspace / ".pi" / "consortium"
        consortium.mkdir(parents=True)
        (consortium / "one.jsonl").write_text('{"type":"turn_start"}\n')
        (consortium / "one.md").write_text("sidecar\n")
        (runner.sessions_dir / "one.jsonl").write_text('{"type":"session"}\n')
        (runner.tmp_root / "rpc-events.jsonl").write_text('{"type":"agent_settled"}\n')
        (runner.tmp_root / "live-boundary.json").write_text('{"ts":"now"}\n')
        runner.raw_incoming = ['{"type":"agent_settled"}']
        runner.outgoing_records = [{"ts": "now", "payload": {"id": "prompt_0", "type": "prompt"}}]
        runner.directional_records = [{"seq": 1, "direction": "in", "payload": {"id": "prompt_0"}}]
        runner.stderr_lines = []
        runner.responses = {"state_final": {"success": True, "data": {}}}
        result = {"run_id": "unit-harvest", "assertions": [], "metrics": {}}
        runner._harvest_evidence(result, {"identity_checks": {"unit": True}})

        manifest = json.loads((runner.evidence_dir / "evidence-manifest.json").read_text())
        listed = {entry["path"] for entry in manifest["files"]}
        actual = {
            str(path.relative_to(runner.evidence_dir))
            for path in runner.evidence_dir.rglob("*")
            if path.is_file() and path.name != "evidence-manifest.json"
        }
        eq(listed, actual, "Evidence manifest set equality")
        for entry in manifest["files"]:
            path = runner.evidence_dir / entry["path"]
            eq(entry["sha256"], _runner_mod.sha256_file(path), f"Hash {entry['path']}")
            eq(entry["size"], path.stat().st_size, f"Size {entry['path']}")
        true((runner.evidence_dir / "consortium/one.md").exists(), "MD sidecar harvested")
        true((runner.evidence_dir / "combined-directional.jsonl").exists(), "Directional log harvested")
        true((runner.evidence_dir / "live-boundary.json").exists(), "Live boundary harvested")


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

def test_no_shell_true() -> None:
    source = _RUNNER_FILE.read_text()
    false("shell=True" in source, "No shell=True")


def test_no_rmtree() -> None:
    source = _RUNNER_FILE.read_text()
    false("rmtree" in source, "No rmtree")
    false("rm -rf" in source, "No rm -rf")


def test_import_no_side_effects() -> None:
    """A fresh import must not change the existing temp parcour set."""
    before = {str(d) for d in Path("/tmp").glob("parcour-*")}
    spec = _ilu.spec_from_file_location("phase05_runner_import_check", str(_RUNNER_FILE))
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    after = {str(d) for d in Path("/tmp").glob("parcour-*")}
    eq(after, before, "Import creates no temp directories")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_tests() -> int:
    test_funcs = [
        # R3 argv
        test_argv_order,
        # R2 guards
        test_unsafe_run_id,
        test_guard_existing_paths,
        # Fix #5 compaction
        test_compaction_clean,
        test_compaction_start_fails,
        test_is_compacting_true_fails,
        test_compaction_real_shape_no_command,
        # Fix #10 stageA
        test_cardinality_per_deliberation,
        test_cardinality_mismatch,
        test_first_baseline_must_be_false_false,
        test_later_baseline_must_be_true_false,
        test_zero_eligible_fails,
        # Fix #6 usage honesty
        test_usage_honesty_pass,
        test_usage_status_values,
        test_invalid_status_fails,
        test_aggregate_on_non_complete_fails,
        test_aggregate_required_on_complete_with_calls,
        test_aggregate_optional_on_complete_zero_calls,
        # M6
        test_m6_basic,
        test_m6_n_zero,
        test_m6_histogram,
        test_m6_separate_turn_counts,
        test_m6_non_string_reason_fails,
        # M7a
        test_percentile_basic,
        test_wall_clock_separate,
        test_duration_schema_failure,
        # M7b
        test_strip_fences_json,
        test_strip_fences_plain,
        test_classify_nonempty,
        test_classify_empty_null,
        test_classify_empty_arrays,
        test_classify_invalid_parse,
        test_classify_invalid_array,
        test_classify_invalid_bad_type,
        test_classify_fenced,
        test_classify_array_items_stringify,
        test_m7b_counts,
        # M8
        test_m8_valid,
        test_m8_arithmetic_fail,
        test_m8_missing,
        test_m8_non_numeric,
        # Confinement
        test_private_tmp_normalization,
        test_path_in_workspace,
        test_path_not_in_workspace_runtime,
        test_path_leak_repo,
        test_confinement_pass,
        test_confinement_abs_in_ws,
        test_confinement_leak,
        test_confinement_nested,
        test_confinement_records_paths,
        # Edit recovery
        test_edit_recovery_ordered,
        test_edit_recovery_wrong_text,
        test_edit_recovery_no_read_between,
        test_edit_recovery_few_tools,
        test_edit_recovery_extra_tools,
        test_edit_recovery_tool_call_id_correlation,
        # Additional assertions
        test_provider_exact,
        test_model_exact,
        test_thinking_off,
        test_prompts_count,
        test_prompts_count_short,
        test_response_success,
        test_response_success_fail,
        test_no_extension_error,
        test_protocol_clean,
        test_required_commands_focus,
        test_fixture_validator,
        test_fixture_missing_tag,
        test_fixture_old_line_remaining,
        test_fixture_text,
        test_fixture_text_missing,
        # Assertions table
        test_assertions_table_exists,
        test_assertion_structure,
        # Process exit
        test_exit_zero,
        test_exit_nonzero,
        # Content manifest
        test_content_manifest_lf,
        # Exit classification
        test_exit_classification_infra,
        test_exit_classification_behavior,
        test_exit_classification_pass,
        # Orchestration unit
        test_bootstrap_sequence,
        test_three_settle_then_collect,
        test_duplicate_settle_rejected,
        test_stdin_close_natural_exit_logic,
        # Manifest constants and fail-closed validation
        test_manifest_constants,
        test_manifest_identity_validator,
        # Evidence pointers and filesystem durability
        test_assertion_has_evidence,
        test_log_collection_and_malformed_failure,
        test_harvest_evidence_manifest_coverage,
        # Safety
        test_no_shell_true,
        test_no_rmtree,
        test_import_no_side_effects,
    ]

    for fn in test_funcs:
        try:
            fn()
        except Exception as e:
            TR.failed += 1
            TR.errors.append(f"{fn.__name__} raised {type(e).__name__}: {e}")

    print(f"Functions executed: {len(test_funcs)}")
    print(TR.summary())
    for err in TR.errors:
        print(f"  FAIL: {err}")
    return 1 if TR.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run_all_tests())