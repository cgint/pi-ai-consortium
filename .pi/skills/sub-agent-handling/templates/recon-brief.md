# RECON BRIEF

Paste into the `task` field. Delete the guidance in angle brackets.

- **Recon ID:** `<nn-topic>` — matches the output filename
- **Role:** Scout (read-only) | Reviewer (read-only)
  (writing work uses `templates/implementation-brief.md`)
- **Goal, one sentence:** `<what this run must establish>`
- **Model:** `olla/qwen36-27b-nvidia-nvfp4:off` (mandatory)
- **Output:** `/Users/cgint/dev/concepts/pi-ai-consortium/agent/inventory/<nn-topic>.md`
  (absolute, plus `outputMode: "file-only"`)

## Mode

READ-ONLY reconnaissance. Do NOT create, modify, or delete any file except your
output file.

## Scope

- **Targets** — absolute paths, explicitly listed. Never "find the relevant
  repos":
  - `<absolute path>`
- **Forbidden paths:** `.env`, `.git/`, anything outside the targets
- **Skip:** `node_modules/`, `deps/`, `_build/`, `venv/`, binaries, generated
  bundles

## Per-target entry, fixed shape

For EACH target, in this order:

- **Path**
- **What it is** — 1-3 sentences from files you ACTUALLY READ, never from the
  directory name
- **Status** — working code | prototype | notes only | empty/abandoned, and the
  files that justify that verdict
- **Language / stack**
- **Last activity** — newest non-git file mtime

## Questions

Numbered, each answerable `YES` + `file:line`, or an explicit `NOT FOUND`.

- **Q1** `<question>`
- **Q2** `<question>` ← **load-bearing: say so if you cannot settle it**

Then: **Most reusable asset** — one schema, script, or concept, or `NONE`.

## Stop rules

- If the premise of this brief turns out to be **materially wrong** — the target
  does not exist, does something entirely different, or the question does not
  apply — **stop and report it. Do not improvise a substitute task.**
- If a question cannot be settled from the sources available, say so plainly.
  Never close a gap with a plausible guess.

## Rules

- Absence is a valid, valuable result. Write `NOT FOUND` explicitly.
- **Never infer capability from a file or directory name** — only from contents
  you read.
- Cite `file:line` for every affirmative claim. Prefer verbatim quotes to
  paraphrase.
- Length cap: under `<N>` lines.

## Required output-file headline

Put the exact headings from `templates/recon-report.md` at the **VERY TOP of the
output file**, before detailed findings. Keep the block under 10 lines.
`outputMode: "file-only"` means there may be no substantive inline return.
