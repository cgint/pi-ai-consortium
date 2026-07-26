#!/usr/bin/env python3
"""Blinded three-pass D5 scorer for c01.

This process never receives an arm or unblinding key.  It accepts one clean
sanitizer bundle, invokes the pinned local model in three fresh tool-free
sessions, validates a closed JSON grammar, and requires exact semantic
unanimity.  It does not retry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
DEFAULT_RUBRIC = HERE / "c01-d5-rubric.txt"
DEFAULT_PROVIDER = Path(
    "/Users/cgint/.pi/profiles/partner/agent/git/github.com/cgint/pi-olla-autodetect/index.ts"
)
MODEL_PROVIDER = "olla"
MODEL_ID = "qwen36-27b-nvidia-nvfp4"
THINKING = "off"
PASSES = 3
SCHEMA_VERSION = "c01-d5-v1"

UNEARNED = {
    "restates_explicit_current_requirement",
    "narrates_routine_editing",
    "repeats_visible_local_error",
}
MISSED = {
    "adopts_stale_format_requirement",
    "drops_compatibility_constraint",
    "changes_durable_objective",
    "violates_current_control_boundary",
}
TOP_KEYS = {
    "schema_version", "bundle_id", "status", "unearned_interruptions",
    "missed_interventions", "ambiguity_reasons",
}
LABEL_KEYS = {"category", "event_index", "evidence_message_indexes", "reason"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _is_index(value: Any, event_count: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= event_count


def _validate_labels(
    labels: Any,
    categories: set[str],
    expected_role: str,
    transcript: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    if not isinstance(labels, list):
        return False, "labels must be an array"
    for position, label in enumerate(labels):
        if not isinstance(label, dict) or set(label) != LABEL_KEYS:
            return False, f"label {position} keys differ from closed schema"
        category = label.get("category")
        if category not in categories:
            return False, f"label {position} has unknown category {category!r}"
        event_index = label.get("event_index")
        if not _is_index(event_index, len(transcript)):
            return False, f"label {position} event_index out of range"
        if transcript[event_index - 1].get("role") != expected_role:
            return False, f"label {position} event role is not {expected_role}"
        evidence = label.get("evidence_message_indexes")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not _is_index(item, len(transcript)) for item in evidence)
            or len(set(evidence)) != len(evidence)
        ):
            return False, f"label {position} evidence indexes invalid"
        if event_index not in evidence:
            return False, f"label {position} evidence omits event_index"
        reason = label.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return False, f"label {position} reason missing"
    return True, "valid"


def validate_output(
    value: Any,
    bundle_id: str,
    transcript: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    if not isinstance(value, dict) or set(value) != TOP_KEYS:
        return False, "top-level keys differ from closed schema"
    if value.get("schema_version") != SCHEMA_VERSION:
        return False, "schema_version mismatch"
    if value.get("bundle_id") != bundle_id:
        return False, "bundle_id mismatch"
    if value.get("status") not in ("scored", "unscorable"):
        return False, "status invalid"
    ambiguity = value.get("ambiguity_reasons")
    if not isinstance(ambiguity, list) or any(not isinstance(x, str) or not x.strip() for x in ambiguity):
        return False, "ambiguity_reasons invalid"
    valid, reason = _validate_labels(
        value.get("unearned_interruptions"), UNEARNED, "additional_context", transcript
    )
    if not valid:
        return False, f"unearned_interruptions: {reason}"
    valid, reason = _validate_labels(
        value.get("missed_interventions"), MISSED, "assistant", transcript
    )
    if not valid:
        return False, f"missed_interventions: {reason}"
    has_labels = bool(value["unearned_interruptions"] or value["missed_interventions"])
    if value["status"] == "scored" and ambiguity:
        return False, "scored output must have no ambiguity reasons"
    if value["status"] == "unscorable":
        if has_labels:
            return False, "unscorable output must not contain labels"
        if not ambiguity:
            return False, "unscorable output requires an ambiguity reason"
    return True, "valid"


def normalize_output(value: Dict[str, Any]) -> List[List[Any]]:
    normalized: List[List[Any]] = []
    for kind, field in (
        ("unearned", "unearned_interruptions"),
        ("missed", "missed_interventions"),
    ):
        for label in value[field]:
            normalized.append([
                kind,
                label["category"],
                label["event_index"],
            ])
    return sorted(normalized, key=lambda x: (x[0], x[1], x[2]))


def aggregate_passes(pass_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    reasons: List[str] = []
    normalized: List[List[List[Any]]] = []
    for record in pass_records:
        if record.get("valid") is not True:
            reasons.append(f"pass {record.get('pass')}: invalid: {record.get('validation_error')}")
            continue
        parsed = record["parsed"]
        if parsed["status"] != "scored":
            reasons.append(f"pass {record.get('pass')}: evaluator returned unscorable")
            continue
        normalized.append(record["normalized_labels"])
    if reasons:
        return {"status": "unscorable", "normalized_labels": [], "reasons": reasons}
    if len(normalized) != PASSES:
        return {"status": "unscorable", "normalized_labels": [], "reasons": ["missing pass output"]}
    if normalized[1:] != normalized[:-1]:
        return {
            "status": "unscorable",
            "normalized_labels": [],
            "reasons": ["semantic disagreement across three passes"],
        }
    return {"status": "scored", "normalized_labels": normalized[0], "reasons": []}


def parse_bundle(path: Path) -> List[Dict[str, Any]]:
    transcript: List[Dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"bundle line {line_number} is invalid JSON: {exc}") from exc
        if not isinstance(value, dict) or value.get("role") not in {
            "user", "assistant", "toolResult", "additional_context"
        }:
            raise ValueError(f"bundle line {line_number} has unsupported role")
        transcript.append(value)
    if not transcript:
        raise ValueError("bundle is empty")
    return transcript


def validate_gate(gate_path: Path, bundle_path: Path, bundle_id: str) -> Dict[str, Any]:
    gate = json.loads(gate_path.read_text())
    if gate.get("clean") is not True or gate.get("bundle_id") != bundle_id:
        raise ValueError("sanitizer gate is not clean for this bundle_id")
    recorded = Path(str(gate.get("bundle", ""))).resolve()
    if recorded != bundle_path.resolve():
        raise ValueError("sanitizer gate bundle path mismatch")
    return gate


def build_command(provider_extension: Path, rubric: str, user_prompt: str) -> List[str]:
    return [
        "pi", "--mode", "text", "--print",
        "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-themes",
        "--no-extensions", "-e", str(provider_extension), "--no-tools", "--no-session",
        "--provider", MODEL_PROVIDER, "--model", MODEL_ID, "--thinking", THINKING,
        "--system-prompt", rubric, user_prompt,
    ]


def redact_command(command: List[str]) -> List[str]:
    redacted = list(command)
    for flag in ("--system-prompt",):
        index = redacted.index(flag) + 1
        value = redacted[index]
        redacted[index] = f"<sha256:{sha256_bytes(value.encode('utf-8'))}>"
    value = redacted[-1]
    redacted[-1] = f"<sha256:{sha256_bytes(value.encode('utf-8'))}>"
    return redacted


def run_pass(
    number: int,
    bundle_id: str,
    transcript: List[Dict[str, Any]],
    bundle_text: str,
    rubric: str,
    provider_extension: Path,
    cwd: Path,
) -> Dict[str, Any]:
    prompt = (
        f"bundle_id: {bundle_id}\n"
        "Transcript JSONL follows. Lines are numbered by their order starting at 1.\n"
        f"{bundle_text}"
    )
    command = build_command(provider_extension, rubric, prompt)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PI_SKIP_VERSION_CHECK": "1"},
        check=False,
    )
    raw = completed.stdout.strip()
    parsed: Optional[Any] = None
    parse_error: Optional[str] = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        parse_error = str(exc)
    valid, validation_error = (False, f"invalid JSON: {parse_error}")
    if parse_error is None:
        valid, validation_error = validate_output(parsed, bundle_id, transcript)
    record: Dict[str, Any] = {
        "pass": number,
        "exit_code": completed.returncode,
        "argv_redacted": redact_command(command),
        "stdout_sha256": sha256_bytes(completed.stdout.encode()),
        "stderr_sha256": sha256_bytes(completed.stderr.encode()),
        "parsed": parsed,
        "valid": completed.returncode == 0 and valid,
        "validation_error": validation_error if not valid else None,
    }
    if record["valid"]:
        record["normalized_labels"] = normalize_output(parsed)
    (cwd / f"pass-{number}.stdout.txt").write_text(completed.stdout)
    (cwd / f"pass-{number}.stderr.txt").write_text(completed.stderr)
    (cwd / f"pass-{number}.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def _identity(value: str, length: int, label: str) -> None:
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"invalid {label} identity")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Blinded unanimous c01 D5 scorer")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--gate", required=True, type=Path)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--provider-extension", type=Path, default=DEFAULT_PROVIDER)
    parser.add_argument("--rubric-sha256", required=True)
    parser.add_argument("--scorer-sha256", required=True)
    args = parser.parse_args(argv)

    try:
        if not re.fullmatch(r"[A-Z][A-Z0-9]{3,15}", args.bundle_id):
            raise ValueError("bundle_id must be opaque uppercase alphanumeric")
        _identity(args.rubric_sha256, 64, "rubric sha256")
        _identity(args.scorer_sha256, 64, "scorer sha256")
        if args.out_dir.exists():
            raise FileExistsError(f"refusing existing scorer output: {args.out_dir}")
        if sha256_file(args.rubric) != args.rubric_sha256:
            raise ValueError("rubric SHA-256 mismatch")
        if sha256_file(Path(__file__).resolve()) != args.scorer_sha256:
            raise ValueError("scorer SHA-256 mismatch")
        validate_gate(args.gate, args.bundle, args.bundle_id)
        transcript = parse_bundle(args.bundle)
        rubric = args.rubric.read_text()
        bundle_text = args.bundle.read_text()
        args.out_dir.mkdir(parents=True)
        records = [
            run_pass(i, args.bundle_id, transcript, bundle_text, rubric, args.provider_extension, args.out_dir)
            for i in range(1, PASSES + 1)
        ]
        aggregate = aggregate_passes(records)
        result = {
            "schema_version": "c01-d5-aggregate-v1",
            "bundle_id": args.bundle_id,
            "passes_required": PASSES,
            "model": {"provider": MODEL_PROVIDER, "id": MODEL_ID, "thinking": THINKING},
            "rubric_sha256": args.rubric_sha256,
            "scorer_sha256": args.scorer_sha256,
            "bundle_sha256": sha256_file(args.bundle),
            "gate_sha256": sha256_file(args.gate),
            "aggregate": aggregate,
        }
        (args.out_dir / "aggregate.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
