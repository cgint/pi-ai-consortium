#!/usr/bin/env python3
"""Emit metadata for recent Pi sessions containing persisted Consortium events.

Reads JSONL only; prints JSONL to stdout. It intentionally does not emit
conversation/tool text, only lengths and narrow evidence flags.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import Any

HISTORY_COMPACTION_LIMIT = 2000
TRUNCATION_RE = re.compile(r"\btruncat(?:e|ed|ion|ing)\b", re.IGNORECASE)
DIRECTIVE_RE = re.compile(
    r"\b(?:clarify|stop|must|before proceeding|do not proceed|require)\b", re.IGNORECASE
)


def text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_content(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        return ""
    return ""


def session_metadata(path: Path) -> dict[str, Any] | None:
    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as source:
            for line in source:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None

    if not any(record.get("customType") == "pi-ai-consortium" for record in records):
        return None

    session_record = next((record for record in records if record.get("type") == "session"), None)
    started_at = session_record.get("timestamp") if isinstance(session_record, dict) else None
    if not isinstance(started_at, str):
        return None
    try:
        started_epoch = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

    active_provider = None
    active_model = None
    roles: Counter[str] = Counter()
    tool_calls: Counter[str] = Counter()
    long_messages = 0
    message_content_chars = 0
    max_message_content_chars = 0
    strict_read_only = False
    events: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        if record.get("type") == "model_change":
            active_provider = record.get("provider")
            active_model = record.get("modelId")

        if record.get("customType") == "discuss-mode":
            data = record.get("data") or {}
            strict_read_only = strict_read_only or data.get("mode") == "read"

        message = record.get("message")
        if isinstance(message, dict):
            role = message.get("role")
            if isinstance(role, str):
                roles[role] += 1
            content = message.get("content")
            content_length = len(text_content(content))
            message_content_chars += content_length
            max_message_content_chars = max(max_message_content_chars, content_length)
            if content_length > HISTORY_COMPACTION_LIMIT:
                long_messages += 1
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "toolCall":
                        name = part.get("name")
                        if isinstance(name, str):
                            tool_calls[name] += 1

        if record.get("customType") != "pi-ai-consortium":
            continue
        data = record.get("data") or {}
        if data.get("kind") != "deliberation":
            continue
        synthesis = str(data.get("synthesis") or "")
        events.append({
            "line": index,
            "timestamp": record.get("timestamp"),
            "provider": active_provider,
            "modelId": active_model,
            "probe_count": data.get("probe_count"),
            "synthesis_length": len(synthesis),
            "synthesis_mentions_truncation": bool(TRUNCATION_RE.search(synthesis)),
            "synthesis_has_directive_language": bool(DIRECTIVE_RE.search(synthesis)),
            "strict_read_only_active": strict_read_only,
        })

    return {
        "path": str(path),
        "session_started_at": started_at,
        "session_started_epoch": started_epoch,
        "message_roles": dict(roles),
        "tool_calls": dict(tool_calls),
        "message_content_chars": message_content_chars,
        "max_message_content_chars": max_message_content_chars,
        "long_message_count": long_messages,
        "deliberation_events": events,
    }


def main() -> int:
    roots = [Path(root) for root in sys.argv[1:]]
    cutoff = time.time() - (14 * 24 * 60 * 60)
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            result = session_metadata(path)
            if result is not None and result["session_started_epoch"] >= cutoff:
                print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
