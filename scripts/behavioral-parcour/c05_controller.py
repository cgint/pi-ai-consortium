#!/usr/bin/env python3
"""Fail-closed, serial c05 planner; it never runs a cell unless asked explicitly."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0, str(HERE))
import c05_runner as runner

REPO_ROOT = HERE.parent.parent
DEFAULT_LEDGER = REPO_ROOT / "docs/c05-evidence/raw-publication-ledger.json"


def sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def load_json(path: Path) -> dict[str, Any]: return json.loads(path.read_text())

def _records(ledger: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = ledger.get("runs")
    ids = [spec["run_id"] for spec in runner.ALL_SPECS]
    if ledger.get("schema_version") != "c05-raw-publication-ledger-v1" or not isinstance(records, list) or [r.get("run_id") for r in records] != ids:
        raise RuntimeError("ledger schedule/order mismatch")
    return records

def next_plan(ledger_path: Path, frozen: Mapping[str, str], *, smoke_decision: Path | None = None) -> dict[str, Any]:
    """Return one exact runner argv, or a mandatory stop; no filesystem mutation."""
    ledger = load_json(ledger_path); records = _records(ledger)
    required = ("freeze_commit", "phase0_sha256", "contract_sha256", "review_sha256")
    if any(not frozen.get(key) for key in required): raise RuntimeError("missing required frozen value")
    statuses = [record.get("status") for record in records]
    if any(status not in ("unconsumed", "consumed") for status in statuses): raise RuntimeError("unknown ledger status")
    first = next((i for i, status in enumerate(statuses) if status == "unconsumed"), None)
    if first is None: return {"state":"complete", "ledger_sha256":sha256(ledger_path)}
    if any(status != "consumed" for status in statuses[:first]): raise RuntimeError("ledger consumption is non-contiguous")
    if any(status != "unconsumed" for status in statuses[first:]): raise RuntimeError("ledger consumption is out of order")
    spec = runner.ALL_SPECS[first]; raw = REPO_ROOT / records[first]["raw_directory"]
    if runner.raw_destination_conflict(raw): raise RuntimeError("existing raw runtime conflict")
    argv = [sys.executable, str(HERE / "c05_runner.py"), "--run-id", spec["run_id"], "--freeze-commit", frozen["freeze_commit"], "--phase0-sha256", frozen["phase0_sha256"], "--contract-sha256", frozen["contract_sha256"], "--review-sha256", frozen["review_sha256"], "--ledger-sha256", sha256(ledger_path), "--consume-ledger"]
    if not spec["smoke"]:
        if smoke_decision is None or not smoke_decision.is_file(): raise RuntimeError("matrix requires committed smoke decision")
        decision_sha = sha256(smoke_decision)
        if not runner.validate_smoke_decision(smoke_decision, decision_sha, ledger): raise RuntimeError("matrix smoke decision is invalid or uncommitted")
        argv += ["--smoke-decision-path", str(smoke_decision), "--smoke-decision-sha256", decision_sha]
    return {"state":"ready", "run_id":spec["run_id"], "smoke":bool(spec["smoke"]), "ledger_sha256":sha256(ledger_path), "argv":argv}

def execute_once(plan: Mapping[str, Any], evidence_dir: Path) -> int:
    """Execute exactly the planned runner invocation once and capture its console."""
    if plan.get("state") != "ready": return 2
    completed = subprocess.run(list(plan["argv"]), text=True, capture_output=True, check=False)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"{plan['run_id']}-console.json").write_text(json.dumps({"run_id":plan["run_id"], "argv":plan["argv"], "returncode":completed.returncode, "stdout":completed.stdout, "stderr":completed.stderr}, indent=2) + "\n")
    return completed.returncode if completed.returncode in (0, 1, 2) else 2

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="c05 serial controller (read-only unless --execute-next)")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER); parser.add_argument("--freeze-commit"); parser.add_argument("--phase0-sha256"); parser.add_argument("--contract-sha256"); parser.add_argument("--review-sha256")
    parser.add_argument("--smoke-decision", type=Path); parser.add_argument("--execute-next", action="store_true"); parser.add_argument("--evidence-dir", type=Path, default=REPO_ROOT / "docs/c05-evidence")
    args = parser.parse_args(argv)
    try:
        plan = next_plan(args.ledger, vars(args), smoke_decision=args.smoke_decision)
        print(json.dumps(plan, indent=2))
        return execute_once(plan, args.evidence_dir) if args.execute_next else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"state":"mandatory-stop", "error":str(exc)})); return 2
if __name__ == "__main__": raise SystemExit(main())
