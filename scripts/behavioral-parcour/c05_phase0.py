#!/usr/bin/env python3
"""Pure c05 Phase 0 capability checks; this module never launches Pi."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

MODEL_PROVIDER = "8081-twins"
MODEL_ID = "qwen36-27b-nvidia-nvfp4"
MODEL_REF = f"{MODEL_PROVIDER}/{MODEL_ID}"
THINKING_LEVEL = "off"
MIN_NODE_MAJOR = 22
# package.json peerDependency: @earendil-works/pi-coding-agent >=0.74.0
MIN_PI_VERSION = (0, 74, 0)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_version(value: str, *, prefix: str = "") -> tuple[int, int, int] | None:
    match = re.fullmatch(rf"{re.escape(prefix)}(\d+)\.(\d+)\.(\d+)", value.strip())
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[union-attr]


def version_provenance(node_output: str, pi_output: str) -> dict[str, Any]:
    node = parse_version(node_output, prefix="v")
    pi = parse_version(pi_output)
    checks = {
        "node_compatible": node is not None and node[0] >= MIN_NODE_MAJOR,
        "pi_compatible": pi is not None and MIN_PI_VERSION <= pi < (1, 0, 0),
    }
    return {"observed": {"node": node_output.strip(), "pi": pi_output.strip()}, "checks": checks, "pass": all(checks.values())}


def validate_extensions(expected: Mapping[Path, str]) -> dict[str, Any]:
    checks = {str(path): path.is_file() and sha256_file(path) == digest for path, digest in expected.items()}
    return {"checks": checks, "pass": bool(checks) and all(checks.values())}


def build_child_env(ambient: Mapping[str, str]) -> dict[str, str]:
    return {**ambient, "PI_SKIP_VERSION_CHECK": "1", "CONSORTIUM_MODEL": MODEL_REF}


def validate_child_env(child: Mapping[str, str], ambient: Mapping[str, str]) -> bool:
    """Validate the built child value; ambient equality to target is valid."""
    del ambient
    return child.get("CONSORTIUM_MODEL") == MODEL_REF


def nested_identity(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    model = data.get("model")
    if not isinstance(model, Mapping):
        return None
    return {"provider": model.get("provider"), "model": model.get("id"), "thinking": data.get("thinkingLevel")}


def validate_executor_state(response: Any, adapter: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] = nested_identity) -> dict[str, Any]:
    data = response.get("data") if isinstance(response, Mapping) else None
    observed = adapter(data) if isinstance(data, Mapping) else None
    observed = observed if isinstance(observed, Mapping) else {}
    checks = {
        "response_success": isinstance(response, Mapping) and response.get("success") is True,
        "provider": observed.get("provider") == MODEL_PROVIDER,
        "model": observed.get("model") == MODEL_ID,
        "thinking": observed.get("thinking") == THINKING_LEVEL,
    }
    return {"checks": checks, "observed": dict(observed), "pass": all(checks.values())}


def settings_spec(workspace: Path, enabled: bool) -> tuple[Path, dict[str, Any]]:
    return workspace / ".pi" / "settings.json", {"consortium": {"enabled": True, "governorMode": "smart_extractor", "stateSupersessionGuard": enabled}}


def validate_settings_spec(workspace: Path, path: Path, payload: Any, enabled: bool) -> bool:
    expected_path, expected_payload = settings_spec(workspace, enabled)
    return path == expected_path and payload == expected_payload


def build_reviewer_command(workspace: Path, sessions: Path, name: str) -> list[str]:
    return [
        "pi", "--mode", "rpc", "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-extensions",
        "--tools", "read", "--provider", MODEL_PROVIDER, "--model", MODEL_ID, "--thinking", THINKING_LEVEL,
        "--session-dir", str(sessions), "--name", name, "--write-guard", str(workspace), "--approve",
    ]


def validate_reviewer_command(command: Sequence[str], workspace: Path, sessions: Path, name: str) -> bool:
    return list(command) == build_reviewer_command(workspace, sessions, name)


def publication_dry_run(authorized_root: Path, run_ids: Sequence[str]) -> dict[str, Any]:
    if not authorized_root.is_absolute() or not authorized_root.is_dir():
        raise ValueError("authorized root must be an existing absolute directory")
    if not run_ids or any(not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) for run_id in run_ids):
        raise ValueError("run IDs must be nonempty safe names")
    destinations = [authorized_root / run_id for run_id in run_ids]
    if len({str(path) for path in destinations}) != len(destinations):
        raise ValueError("run IDs must be unique")
    root = authorized_root.resolve()
    if any(destination.resolve().parent != root for destination in destinations):
        raise ValueError("publication destination escapes authorized root")
    conflicts = [str(path) for path in destinations if path.exists()]
    return {"authorized_root": str(root), "destinations": [str(path) for path in destinations], "conflicts": conflicts, "pass": not conflicts, "dry_run": True}


def serialize_settings(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
