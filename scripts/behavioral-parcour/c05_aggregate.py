#!/usr/bin/env python3
"""Deterministic c05 final-result aggregation; never makes pooled score or cost claims."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c05_runner as runner


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def verify_raw(record: Mapping[str, Any], raw_root: Path) -> dict[str, Any]:
    raw = raw_root / str(record["run_id"])
    result_path, manifest_path = raw / "result.json", raw / "evidence-manifest.json"
    if not result_path.is_file() or not manifest_path.is_file() or record.get("result_sha256") != sha256(result_path):
        raise RuntimeError(f"{record['run_id']}: result identity/hash mismatch")
    result, manifest = _load(result_path), _load(manifest_path)
    files = manifest.get("files")
    if result.get("run_id") != record["run_id"] or not isinstance(files, list):
        raise RuntimeError(f"{record['run_id']}: result/manifest identity mismatch")
    listed = {item.get("path"): item for item in files if isinstance(item, Mapping) and isinstance(item.get("path"), str)}
    if not any(str(name).startswith("sessions/") and str(name).endswith(".jsonl") for name in listed) or not any(str(name).startswith("consortium/") and str(name).endswith(".jsonl") for name in listed):
        raise RuntimeError(f"{record['run_id']}: missing process evidence")
    for name, item in listed.items():
        target = raw / str(name)
        if not target.is_file() or item.get("sha256") != sha256(target) or item.get("size") != target.stat().st_size:
            raise RuntimeError(f"{record['run_id']}: evidence byte mismatch")
    required = ("identity_valid", "process_valid", "prompts_delivered", "raw_valid", "continuity", "control_regression", "guard_fired", "failed_assertions")
    if any(key not in result for key in required) or result["prompts_delivered"] != 3:
        raise RuntimeError(f"{record['run_id']}: incomplete identity/process/prompts/raw result")
    return result


def aggregate(ledger_path: Path, raw_root: Path) -> dict[str, Any]:
    ledger = _load(ledger_path)
    records = ledger.get("runs")
    expected_ids = [spec["run_id"] for spec in runner.ALL_SPECS]
    if ledger.get("schema_version") != "c05-raw-publication-ledger-v1" or not isinstance(records, list) or [record.get("run_id") for record in records] != expected_ids or any(record.get("status") != "consumed" for record in records):
        raise RuntimeError("requires final 56 consumed ledger results in exact runner schedule order")
    results = [verify_raw(record, raw_root) for record in records]
    smoke, matrix = results[:len(runner.SMOKE_SPECS)], results[len(runner.SMOKE_SPECS):]
    positives = [result for result in matrix if result.get("fixture_kind") == "positive"]
    controls = [result for result in matrix if result.get("fixture_kind") == "control"]
    on_pos = [result for result in positives if result.get("arm") == "on"]
    off_pos = [result for result in positives if result.get("arm") == "off"]
    on_controls = [result for result in controls if result.get("arm") == "on"]
    if len(smoke) != 8 or len(matrix) != 48 or len(on_pos) != len(off_pos) != 12 or len(controls) != 24 or len(on_controls) != 12:
        raise RuntimeError("invalid c05 smoke/matrix denominator")
    pairs: list[dict[str, Any]] = []
    for repetition in (1, 2, 3):
        for fixture_id in runner.FIXTURE_ORDER:
            paired = [result for result in matrix if result.get("repetition") == repetition and result.get("fixture_id") == fixture_id]
            if [result.get("arm") for result in paired] != ["off", "on"]:
                raise RuntimeError("matrix lacks exact OFF/ON paired runner records")
            pairs.append({"fixture_id": fixture_id, "repetition": repetition, "off": paired[0], "on": paired[1]})
    mandatory_behavioral_gates = all(
        result.get("identity_valid") is True and result.get("process_valid") is True and result.get("raw_valid") is True and not result.get("failed_assertions")
        for result in results
    )
    smoke_transition = runner.smoke_transition(smoke) and all(not result.get("failed_assertions") for result in smoke)
    on_fires = sum(result.get("guard_fired") is True for result in on_pos)
    off_fires = sum(result.get("guard_fired") is True for result in off_pos)
    control_fires = sum(result.get("guard_fired") is True for result in controls)
    on_control_fires = sum(result.get("guard_fired") is True for result in on_controls)
    regressions = sum(result.get("control_regression") is True for result in controls)
    on_count = sum(result["continuity"] is True for result in on_pos)
    off_count = sum(result["continuity"] is True for result in off_pos)
    mechanism = on_fires == 12 and off_fires == 0 and control_fires == 0
    uplift = mandatory_behavioral_gates and smoke_transition and mechanism and on_count >= 11 and on_count - off_count >= 3 and regressions == 0
    return {
        "schema_version": "c05-aggregate-v1",
        "smoke_records": smoke,
        "smoke_transition": smoke_transition,
        "cell_records": matrix,
        "paired_records": pairs,
        "denominators": {"smoke": 8, "matrix": 48, "on_positive": 12, "off_positive": 12, "controls": 24, "on_controls": 12},
        "mechanism": {"on_positive_fires": on_fires, "off_positive_fires": off_fires, "control_fires": control_fires, "on_control_fires": on_control_fires, "pass": mechanism},
        "continuity": {"on": on_count, "off": off_count, "delta": on_count - off_count},
        "controls": {"fires": control_fires, "on_fires": on_control_fires, "regressions": regressions},
        "mandatory_behavioral_gates_pass": mandatory_behavioral_gates,
        "bounded_uplift": uplift,
        "wall_clock_ms": {"on": sum(result.get("wall_clock_ms", 0) for result in matrix if result.get("arm") == "on"), "off": sum(result.get("wall_clock_ms", 0) for result in matrix if result.get("arm") == "off")},
        "tool_calls": {"on": sum(result.get("tool_calls", 0) for result in matrix if result.get("arm") == "on"), "off": sum(result.get("tool_calls", 0) for result in matrix if result.get("arm") == "off")},
    }
