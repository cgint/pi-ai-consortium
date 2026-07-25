# IMPLEMENTATION BRIEF

Paste into the `task` field. Delete guidance in angle brackets.

- **Change ID:** `<nn-topic>` — matches the output filename
- **Role:** Worker (writes)
- **Objective, one sentence:** `<observable code outcome>`
- **Model:** `olla/qwen36-27b-nvidia-nvfp4:off` (mandatory)
- **Async:** `true` (mandatory)
- **Output:** `/absolute/repo-owned/path/<nn-topic>.md`
  (`outputMode: "file-only"`)

## Authorization boundary

- **Authorized behavior change:** `<exactly what may change, or NONE — telemetry only>`
- **Must remain invariant:** `<prompts, call count/order, visible output, governor, etc.>`
- **Do not broaden scope.** If satisfying the objective requires another behavior
  change, STOP and report `scope-blocked`; do not improvise.

## Write scope

- **May modify** — absolute paths, explicitly listed:
  - `<absolute path>`
- **May create:** `<exact paths or NONE>`
- **Forbidden:** `.env*`, `.git/`, goal/session/run evidence, files outside this
  list, dependency manifests unless explicitly authorized
- Do not commit. The main session reviews and commits after independent
  validation.

## Required implementation

Number each requirement so the report can map it to evidence.

1. `<requirement + exact semantics>`
2. `<requirement + edge/failure semantics>`
3. `<test requirement>`

## Verification

Run only the listed commands; record command + exit code + concise result.

1. `<targeted test command>`
2. `<typecheck/lint command>`
3. `<full repo check when proportionate>`

## Stop rules

- If the premise is materially wrong, STOP and report `premise-wrong`.
- If an allowed file has overlapping pre-existing edits, STOP and report them;
  never overwrite or revert another change.
- If verification fails twice for the same unexplained reason, STOP and report
  the exact failure; do not weaken tests or requirements.
- If a dependency, migration, destructive operation, or unlisted file becomes
  necessary, STOP and ask through intercom.
- Absence and inability are valid results. Never fake verification.

## Required output file

Put the exact headline block from `templates/implementation-report.md` at the
VERY TOP, before implementation notes. Under it include:

- every numbered requirement mapped to `PASS`, `FAIL`, or `UNDETERMINED`, with
  changed file:line and covering test for each `PASS`;
- files changed;
- commands run and exit codes;
- residual risks / runtime-only checks;
- no more than 160 lines total.

**Completion rule:** status `complete` is valid only when every numbered
requirement is `PASS`. If any required behavior is deferred, absent, or only
covered by callback/unit tests while production wiring is untested, report
`partial` or `scope-blocked` even when every command is green.
