#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
here = repo / "scripts" / "behavioral-parcour"
sys.path.insert(0, str(here))
import c05_phase0_probe as probe

run_id = "c05-patch-compatibility-schema-0842"
probe.RUN_ID = run_id
probe.RUN_ROOT = repo / ".parcour-runs" / run_id
probe.EVIDENCE_ROOT = repo / "docs" / "c05-evidence" / run_id
probe.WORKSPACE = probe.RUN_ROOT / "workspace"
probe.SESSIONS = probe.RUN_ROOT / "sessions"
probe.RESULT = probe.RUN_ROOT / "result.json"

result = probe.run_live()
print(json.dumps({"run_id": run_id, "result": str(probe.RESULT), "pass": result["pass"], "checks": result["checks"]}, indent=2))
raise SystemExit(0 if result["pass"] else 1)
