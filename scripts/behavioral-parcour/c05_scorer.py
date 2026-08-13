#!/usr/bin/env python3
"""c05-owned semantic continuity scorer for the c04 separator defect only."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
CORPUS_PATH = HERE / "c05-supersession-corpus.json"
HISTORICAL_WORDS = ("supersed", "histor", "replac", "former", "previous", "retired", "migrated")


def _contexts(pattern: str, text: str) -> Iterable[str]:
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        yield text[max(0, match.start() - 100):match.end() + 100].lower()


def _markdown_has_current_framing(match: re.Match[str], final_text: str) -> bool:
    """Require a local, affirmative current label for a Markdown identity."""
    line_start = final_text.rfind("\n", 0, match.start()) + 1
    line_end = final_text.find("\n", match.end())
    line_end = len(final_text) if line_end < 0 else line_end
    line = final_text[line_start:line_end]
    identity = match.group(0)
    explicit_identity_negated_current = (
        re.escape(identity)
        + r"(?:\s+(?:requirement|policy))?\s+(?:is|are|remains?)\s+"
        + r"(?:not|never)\s+(?:(?:a|the)\s+)?current(?:\s+durable)?(?:\s+(?:requirement|policy))?\b"
    )
    if re.search(explicit_identity_negated_current, line, flags=re.IGNORECASE):
        return False
    if re.search(r"\b(?:not|no|never)(?:\s+longer)?\s+current\b", line, flags=re.IGNORECASE):
        return False

    before_identity = line[:match.start() - line_start]
    label = r"\bcurrent(?:\s+durable)?\s+(?:requirement|policy)\b"
    explicit_identity_current = re.escape(identity) + r"\s+(?:is|are|remains?)\s+current\b"
    if re.search(label, before_identity, flags=re.IGNORECASE):
        return True
    if re.search(explicit_identity_current, line, flags=re.IGNORECASE):
        return True

    previous_line_end = line_start - 1
    if previous_line_end < 0:
        return False
    previous_line_start = final_text.rfind("\n", 0, previous_line_end) + 1
    previous_line = final_text[previous_line_start:previous_line_end]
    return bool(re.fullmatch(r"\s*(?:#+\s*)?current(?:\s+durable)?\s+(?:requirement|policy)\s*:?\s*", previous_line, flags=re.IGNORECASE))


def _requirement_replacement_passes(final_text: str) -> bool:
    """Require current Markdown and historical YAML policy identities.

    The policy identity permits only the release-notes separator to be a space
    or hyphen. Current and historical framing remain mandatory.
    """
    current = any(
        _markdown_has_current_framing(match, final_text)
        for match in re.finditer(r"\bmarkdown\s+release(?:[\s-]+)notes\b", final_text, flags=re.IGNORECASE)
    )
    historical = any(
        any(word in context for word in HISTORICAL_WORDS)
        for context in _contexts(r"\byaml\s+release(?:[\s-]+)notes\b", final_text)
    )
    return current and historical and "release_stream=stable" in final_text.lower()


def continuity_passes(fixture: Dict[str, Any], final_text: str) -> bool:
    """Return whether a positive fixture retains its current and old policies."""
    if fixture.get("kind") != "positive":
        return True
    if fixture.get("id") == "requirement-replacement":
        return _requirement_replacement_passes(final_text)

    lower = final_text.lower()
    current = all(marker.lower() in lower for marker in fixture.get("current_markers", []))
    historical = True
    for marker in fixture.get("historical_markers", []):
        needle = marker.lower()
        position = lower.find(needle)
        if position < 0:
            historical = False
            continue
        context = lower[max(0, position - 100):position + len(needle) + 100]
        if not any(word in context for word in HISTORICAL_WORDS):
            historical = False
    return current and historical
