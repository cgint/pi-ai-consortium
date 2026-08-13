#!/usr/bin/env python3
"""c05 Phase 0 zero-user-prompt RPC capability probe.

``--dry-run`` is side-effect free.  Live mode is intentionally explicit and
sends only two ``get_state`` RPC control commands; it never sends a prompt.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import c05_phase0 as phase0
import phase05_runner as paths

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "c05-phase0-capability"
RUN_ROOT = REPO_ROOT / ".parcour-runs" / RUN_ID
WORKSPACE = RUN_ROOT / "workspace"
SESSIONS = RUN_ROOT / "sessions"
RESULT = RUN_ROOT / "result.json"
RPC_METHODS = ("get_state", "get_state")


def confined(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def build_pi_command(workspace: Path, sessions: Path) -> list[str]:
    return [
        "pi", "--mode", "rpc", "--no-context-files", "--no-skills", "--no-prompt-templates",
        "--no-extensions", "--tools", "read",
        "-e", str(paths.PROVIDER_EXT), "-e", str(paths.CONSORTIUM_EXT), "-e", str(paths.FOCUS_EXT),
        "--provider", phase0.MODEL_PROVIDER, "--model", phase0.MODEL_ID, "--thinking", phase0.THINKING_LEVEL,
        "--dm-off", "--write-guard", str(workspace), "--approve",
        "--session-dir", str(sessions), "--name", RUN_ID,
    ]


def protocol_commands() -> list[dict[str, str]]:
    return [
        {"id": "state_initial", "type": "get_state"},
        {"id": "state_final", "type": "get_state"},
    ]


def extension_provenance() -> dict[str, str]:
    extensions = (paths.PROVIDER_EXT, paths.CONSORTIUM_EXT, paths.FOCUS_EXT)
    return {str(path): phase0.sha256_file(path) for path in extensions}


def build_plan(ambient: Mapping[str, str]) -> dict[str, Any]:
    settings_path, settings = phase0.settings_spec(WORKSPACE, enabled=True)
    command = build_pi_command(WORKSPACE, SESSIONS)
    extension_hashes = extension_provenance()
    reviewer = phase0.build_reviewer_command(WORKSPACE, SESSIONS, f"{RUN_ID}-review")
    confinement = all(confined(path) for path in (RUN_ROOT, WORKSPACE, SESSIONS, RESULT, settings_path))
    return {
        "schema_version": "c05-phase0-probe-plan-v1",
        "run_id": RUN_ID,
        "paths": {"run_root": str(RUN_ROOT), "workspace": str(WORKSPACE), "sessions": str(SESSIONS), "result": str(RESULT)},
        "settings": {"path": str(settings_path), "payload": settings, "serialized": phase0.serialize_settings(settings)},
        "command": command,
        "child_environment": {key: phase0.build_child_env(ambient)[key] for key in ("CONSORTIUM_MODEL", "PI_SKIP_VERSION_CHECK")},
        "extension_hashes": extension_hashes,
        "rpc_commands": protocol_commands(),
        "reviewer_command": reviewer,
        "checks": {
            "path_confinement": confinement,
            "settings_exact": phase0.validate_settings_spec(WORKSPACE, settings_path, settings, enabled=True),
            "extensions": phase0.validate_extensions({Path(path): digest for path, digest in extension_hashes.items()})["pass"],
            "zero_user_prompts": all(command["type"] != "prompt" for command in protocol_commands()),
            "only_get_state": tuple(command["type"] for command in protocol_commands()) == RPC_METHODS,
            "reviewer_command_exact": phase0.validate_reviewer_command(reviewer, WORKSPACE, SESSIONS, f"{RUN_ID}-review"),
        },
    }


def validate_plan(plan: Mapping[str, Any]) -> list[str]:
    checks = plan.get("checks")
    if not isinstance(checks, Mapping):
        return ["missing plan checks"]
    return [name for name, passed in checks.items() if passed is not True]


def _command_output(command: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {"argv": list(command), "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _read_response(proc: subprocess.Popen[bytes], raw_stdout: list[str], raw_stderr: list[str]) -> dict[str, Any]:
    assert proc.stdout is not None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        ready, _, _ = select.select([proc.stdout], [], [], 0.25)
        if not ready:
            if proc.poll() is not None:
                break
            continue
        line = proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        raw_stdout.append(text)
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "response" and event.get("id") in {"state_initial", "state_final"}:
            return event
    raise RuntimeError("mandatory get_state response missing")


def run_live() -> dict[str, Any]:
    """Execute exactly one non-retrying control-only probe and write one result."""
    plan = build_plan(dict(os.environ))
    failures = validate_plan(plan)
    if failures:
        raise RuntimeError(f"invalid probe plan: {failures}")
    if RUN_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite existing probe root: {RUN_ROOT}")
    RUN_ROOT.mkdir(parents=True)
    WORKSPACE.mkdir()
    SESSIONS.mkdir()
    settings_path = Path(plan["settings"]["path"])
    settings_path.parent.mkdir()
    settings_path.write_text(str(plan["settings"]["serialized"]))
    publication = phase0.publication_dry_run(REPO_ROOT / "docs", [RUN_ID])
    versions = {"node": _command_output(["node", "--version"]), "pi": _command_output(["pi", "--version"])}
    version_check = phase0.version_provenance(versions["node"]["stdout"], versions["pi"]["stdout"])
    raw_stdout: list[str] = []
    raw_stderr: list[str] = []
    states: dict[str, Any] = {}
    process_returncode: int | None = None
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(plan["command"], cwd=WORKSPACE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=phase0.build_child_env(dict(os.environ)))
        assert proc.stdin is not None
        for command in protocol_commands():
            proc.stdin.write((json.dumps(command, separators=(",", ":")) + "\n").encode())
            proc.stdin.flush()
            states[command["id"]] = _read_response(proc, raw_stdout, raw_stderr)
        proc.stdin.close()
        process_returncode = proc.wait(timeout=30)
        if proc.stderr is not None:
            raw_stderr.extend(proc.stderr.read().decode("utf-8", errors="replace").splitlines())
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        if proc is not None and proc.poll() is None:
            proc.terminate()
            process_returncode = proc.wait(timeout=30)
        if proc is not None and proc.stderr is not None:
            raw_stderr.extend(proc.stderr.read().decode("utf-8", errors="replace").splitlines())
    else:
        failure = None
    identity = {name: phase0.validate_executor_state(state) for name, state in states.items()}
    checks = {**plan["checks"], "versions": version_check["pass"], "publication_dry_run": publication["pass"], "initial_state": identity.get("state_initial", {}).get("pass") is True, "final_state": identity.get("state_final", {}).get("pass") is True, "process_exit": process_returncode == 0, "execution": failure is None}
    result = {"schema_version": "c05-phase0-probe-result-v1", "plan": plan, "versions": versions, "version_check": version_check, "publication_dry_run": publication, "states": states, "identity": identity, "raw_streams": {"stdout": raw_stdout, "stderr": raw_stderr}, "process_returncode": process_returncode, "failure": failure, "pass": all(value is True for value in checks.values()), "checks": checks}
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        plan = build_plan(dict(os.environ))
        print(json.dumps({"plan": plan, "pass": not validate_plan(plan)}, indent=2, sort_keys=True))
        return 0 if not validate_plan(plan) else 1
    result = run_live()
    print(json.dumps({"result": str(RESULT), "pass": result["pass"]}, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
