#!/usr/bin/env python3
"""Derive a scorer-facing bundle from a raw Pi session, deterministically.

Implements plan §12.2. Two guarantees:

  1. Structural stripping. Only `message` entries survive, and within them only a
     whitelisted set of fields. This removes provider/model/api/responseId/usage,
     session and run identifiers, timestamps, and the cwd path without relying on
     pattern matching.
  2. Declared aliasing. Scenario-specific literals are replaced from a versioned
     alias map. No ad hoc edits.

The deny-list scan is a hard gate. A bundle with any hit is quarantined and must
be re-derived, never hand-patched.

Usage:
    sanitize_bundle.py --session RAW.jsonl --alias-map MAP.json \
                       --bundle-id B001 --out-dir DIR [--deny-list FILE]

Exit codes: 0 clean, 3 quarantined, 2 usage/input error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DENY_LIST = HERE / "deny-list.txt"

# Fields kept per role. Everything else is dropped, including model provenance
# that Pi attaches to assistant messages (api/provider/model/responseId/usage).
KEEP = {
    "user": ("role", "content"),
    "assistant": ("role", "content", "stopReason"),
    "toolResult": ("role", "toolName", "content", "isError"),
}

# Content-part fields kept, by part type.
KEEP_PART = {
    "text": ("type", "text"),
    "toolCall": ("type", "name", "arguments"),
}

# Consortium guidance, when present, is relabelled neutrally so the evaluator
# cannot identify the arm from the label alone.
NEUTRAL_CONTEXT_LABEL = "additional_context"


def load_alias_map(path: Path) -> tuple[dict, list[tuple[str, str]]]:
    data = json.loads(path.read_text())
    literals = data.get("literals", {})
    # Longest first so a shorter key cannot pre-empt a longer overlapping one.
    ordered = sorted(literals.items(), key=lambda kv: len(kv[0]), reverse=True)
    return data, ordered


def load_deny_list(path: Path) -> list[tuple[str, re.Pattern]]:
    patterns = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append((line, re.compile(line)))
    return patterns


def apply_aliases(value, ordered: list[tuple[str, str]]):
    if isinstance(value, str):
        for src, dst in ordered:
            value = value.replace(src, dst)
        return value
    if isinstance(value, list):
        return [apply_aliases(item, ordered) for item in value]
    if isinstance(value, dict):
        return {key: apply_aliases(item, ordered) for key, item in value.items()}
    return value


def sanitize_part(part):
    if not isinstance(part, dict):
        return None
    kind = part.get("type")
    keep = KEEP_PART.get(kind)
    if keep is None:
        # Unknown part types are dropped rather than passed through, so a future
        # Pi schema addition cannot silently leak provenance into a bundle.
        return {"type": "omitted", "reason": f"unsupported part type: {kind}"}
    return {field: part[field] for field in keep if field in part}


def sanitize_message(entry: dict):
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    keep = KEEP.get(role)
    if keep is None:
        return None
    out = {}
    for field in keep:
        if field not in message:
            continue
        if field == "content" and isinstance(message[field], list):
            parts = [sanitize_part(part) for part in message[field]]
            out[field] = [part for part in parts if part]
        else:
            out[field] = message[field]
    return out


def sanitize_custom(entry: dict):
    """Relabel one observed production deliberation entry neutrally.

    Pi persists consortium guidance as a custom entry whose payload is nested
    under ``data``.  Fail closed on every other custom envelope so unrelated
    extension content cannot silently enter a scorer bundle.
    """
    if entry.get("type") not in ("custom", "custom_entry"):
        return None
    if entry.get("customType") != "pi-ai-consortium":
        return None
    data = entry.get("data")
    if not isinstance(data, dict) or data.get("kind") != "deliberation":
        return None
    text = data.get("synthesis")
    if not isinstance(text, str) or not text:
        return None
    return {"role": NEUTRAL_CONTEXT_LABEL, "content": [{"type": "text", "text": text}]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, type=Path)
    ap.add_argument("--alias-map", required=True, type=Path)
    ap.add_argument("--bundle-id", required=True)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--deny-list", type=Path, default=DEFAULT_DENY_LIST)
    ap.add_argument("--arm", default="unspecified", help="recorded in the unblinding key only")
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Z][A-Z0-9]{3,15}", args.bundle_id):
        print("error: bundle-id must be opaque uppercase alphanumeric", file=sys.stderr)
        return 2
    if not args.session.exists():
        print(f"error: session not found: {args.session}", file=sys.stderr)
        return 2

    key_path = args.out_dir.parent / "unblinding" / f"{args.bundle_id}.json"
    output_targets = [
        args.out_dir / f"{args.bundle_id}.jsonl",
        args.out_dir / f"{args.bundle_id}.jsonl.QUARANTINED",
        args.out_dir / f"{args.bundle_id}.gate.json",
        key_path,
    ]
    existing = [str(path) for path in output_targets if path.exists()]
    if existing:
        print(f"error: refusing existing bundle artifacts: {existing}", file=sys.stderr)
        return 2

    alias_meta, ordered = load_alias_map(args.alias_map)
    deny = load_deny_list(args.deny_list)

    kept, dropped = [], []
    for raw in args.session.read_text(errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"error: malformed session line: {exc}", file=sys.stderr)
            return 2
        etype = entry.get("type")
        if etype == "message":
            item = sanitize_message(entry)
        elif etype in ("custom", "custom_entry"):
            item = sanitize_custom(entry)
        else:
            dropped.append(etype)
            continue
        if item:
            kept.append(apply_aliases(item, ordered))
        else:
            dropped.append(etype)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(item, separators=(",", ":")) for item in kept) + "\n"

    hits = []
    for label, pattern in deny:
        for match in pattern.finditer(body):
            hits.append({"pattern": label, "match": match.group(0)})

    clean = not hits
    suffix = "" if clean else ".QUARANTINED"
    bundle_path = args.out_dir / f"{args.bundle_id}.jsonl{suffix}"
    bundle_path.write_text(body)

    report = {
        "bundle_id": args.bundle_id,
        "clean": clean,
        "bundle": str(bundle_path),
        "alias_map": {"id": alias_meta.get("map_id"), "version": alias_meta.get("version")},
        "entries_kept": len(kept),
        "entry_types_dropped": sorted(set(dropped)),
        "deny_list_hits": hits,
    }
    (args.out_dir / f"{args.bundle_id}.gate.json").write_text(json.dumps(report, indent=2) + "\n")

    # The unblinding key is written outside the bundle directory by the caller's
    # convention; here it is a sibling file the scoring pass must not read.
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(
        json.dumps(
            {
                "bundle_id": args.bundle_id,
                "arm": args.arm,
                "raw_session": str(args.session),
                "alias_map": alias_meta.get("map_id"),
            },
            indent=2,
        )
        + "\n"
    )

    print(json.dumps(report, indent=2))
    return 0 if clean else 3


if __name__ == "__main__":
    sys.exit(main())
