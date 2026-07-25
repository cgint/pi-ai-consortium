---
name: sub-agent-handling
description: How this repo delegates ground work to subagents. Use when about to call the subagent tool - covers the mandatory local model, file-based reporting with outputMode file-only and absolute output paths, the required headline-bearing short return, and the task-brief shape that demands NOT FOUND answers and file:line citations. Read before delegating, not after.
---

# Sub-agent handling

## Status

The main session works at **architect level**. Tedious ground work — exhaustive
doc reads, code recon, inventories, "does X exist anywhere" questions — is
delegated. The main session is too expensive to spend on it.

Every rule below is derived from a **measured failure or success in this repo**,
dated. None of it is style preference. Where a rule has a date, it was verified;
treat undated additions as provisional.

## Flow

```text
  1. PREPARE          templates/recon-brief.md
     bounded targets, questions, allowed + forbidden paths, stop rules
            |
  2. DELEGATE         model pinned, absolute output path, outputMode file-only
            |
  3. RUN              scout works inside the brief; on a wrong premise it
                      STOPS and reports rather than improvising
            |
  4. SHORT RETURN     templates/recon-report.md
     HEADLINE + CONTRADICTS are the two lines that matter
            |
  5. LIFT + CORRECT   move decision-relevant content into a repo-owned file;
                      correct the record where the report falsified something
```

## When to use

Delegate when the work is:

- **bounded** — a named set of directories, files, or questions
- **mechanical** — reading, listing, grepping, inventorying, citing
- **verbose** — the answer is long but only a few lines of it change a decision
- **parallelisable** — several independent clusters can be scouted at once

Do **not** delegate:

- the decision itself, or any judgement call
- writing that must be consistent with repo voice and prior rulings
- anything where a wrong-but-fluent answer would be hard to detect

## Non-negotiables

### 0. Always launch asynchronously; the main session remains the overseer

**Every sub-agent run must pass `async: true`.** The main session must remain
available while children work — both to advance independent architect-level work
and, more importantly, to answer child questions through `pi-intercom` so the
child can continue with corrected guidance.

A foreground run on 2026-07-25 blocked the main session until both scouts had
finished. That defeated the intended supervision model: the lead could neither
inspect other evidence nor respond if a child discovered a wrong premise and
needed clarification.

Operating loop:

1. launch with `async: true`;
2. keep the main session free for judgement, independent reads, and coordination;
3. **do not poll** `status`, `intercom pending`, transcripts, or output files;
   Pi automatically notifies the main session on completion, attention, or a
   child question;
4. respond through `intercom` or steer only **after** such a notification — the
   point of async is availability, not active surveillance;
5. do **not** call `subagent_wait` merely to idle until completion — return control
   and let Pi wake the session, unless the current turn truly cannot finish
   without the result;
6. after completion, read only the headline block and decision-bearing citations.

This rule applies to single, parallel, and chained delegation. Async execution is
not permission to abandon children; it is what makes live supervision possible.
**Notification-driven does not mean inattentive:** answer immediately when Pi
surfaces a child question or attention signal, but never probe merely to see if
one exists.

**Do not request `acceptance: "checked"` for a read-only analysis/review.**
Verified 2026-07-25: the advisor completed a 144-line review and wrote its output,
but the run was marked failed because checked acceptance required command-run
evidence that a read-only review had no reason to produce. Omit acceptance for
read-only scouts/advisors; reserve checked/verified acceptance for execution work
with an actual verification command. Also do not request `reviewed` from a
single read-only run — the runtime correctly rejects it when no independent
reviewer can be supplied.

### 1. Model

**Always** pass `model: "olla/qwen36-27b-nvidia-nvfp4:off"` — the local model with
thinking off.

A run on 2026-07-25 failed outright because the model was omitted and a default
was resolved: `No models match pattern "olla/deepseek-v4-flash-dspark"`. Omitting
the model is not a soft default; it breaks the run.

### 2. Reports go to files, not into the transcript

Ground-work reports are large. Do not pull them into context wholesale.

- Pass **`outputMode: "file-only"`** together with `output`. The default returns
  the full report inline **and** writes the file — paying twice. Measured
  2026-07-25: 60 KB of report text came back inline while the identical text sat
  on disk.
- **`output` must be an absolute path.** Verified 2026-07-25: `output:
  "agent/inventory/06-x.md"` did **not** create `agent/inventory/`; the relative
  path resolved inside the run's own artifact directory. Use
  `/Users/cgint/dev/concepts/deliberate-agent/agent/inventory/<n>-<topic>.md`.
- **A write guard silently redirects delegation.** Verified 2026-07-25 across 11
  runs: when `output` points outside the write-guard root (here
  `/Users/cgint/dev-external/pi-ai-consortium`), the child **cannot write it**.
  It falls back to returning the artifact inline and the runtime persists the
  file. The file *does* land at the absolute path — but see rule 3 for the cost.
  If reports must live in another repo, expect this path, or point `output`
  inside the guarded root and lift afterwards.
- **`.pi-subagents/` is gitignored** (`.gitignore:11`) — anything left there is
  transient. Report content that will inform a decision must be lifted into a
  repo-owned file (`docs/`, or `agent/inventory/` for raw recon). This already
  cost real work once: `docs/pi-extension-capabilities.md` had to be hand-copied
  out of an artifact before it was lost.

### 3. The short return must carry the headline, not a status

**Put the block at the TOP of the output file.** Verified 2026-07-25:
`outputMode: "file-only"` replaces the inline return with just a path and byte
count, so a headline placed in the *inline* return never arrives, and a headline
at the *bottom* of the file requires reading the whole report to reach. Instruct
explicitly: *"put this block at the VERY TOP of your output file, before anything
else."*

**A write guard defeats "headline first," and instructing against it does not
help.** Verified 2026-07-25: when the output path is outside the write-guard
root, the child prepends an explanation — *"The write path is outside the allowed
directory…"* — **above** the headline block. Adding an explicit `FORMAT RULE, READ
FIRST: no preamble` to the brief did **not** suppress it; runs 05-11 all still
prepended 1-5 lines. Consequence for the lead session: read the first ~20 lines,
not the first line, and strip the preamble when lifting content. Do not assume
line 1 is the headline.

Require at most ~10 lines containing:

1. the output file path;
2. **the single most decision-relevant finding**, stated as a fact;
3. anything that **contradicts** the premise of the task, flagged explicitly;
4. every `NOT FOUND` that was load-bearing;
5. what it could not determine, and why.

**"Completed successfully, see the file" is a failed report.** A subagent can
finish flawlessly and still overturn the premise it was given, so a green status
line is nearly worthless.

Rationale, 2026-07-25: the most valuable result of a five-scout run was that
`/inspect` emits **14** claim categories and *not* only `:permission` —
falsifying a belief this project had built on for days. A status line would have
concealed it, and the summary would have been trusted without opening the file.
**Design the return so a contradiction cannot be silent.**

### 4. Absence must be sayable

Every task must demand explicit `NOT FOUND` / `NOT SUPPORTED` answers and
`file:line` citations.

- Absence is a valid, valuable result. Fabrication is not.
- Forbid inference from names: *"NEVER infer capability from a file or directory
  name, only from contents you actually read."* This matters — a 2026-07-25 scan
  found `hindsight-test-lab` (sounds like hindsight analysis; actually a test
  harness for a commercial KB product) and `cline-memory` (sounds like agent
  memory; actually a card-matching game).
- Require `file:line` for every affirmative claim, so the main session can spot-check
  cheaply.

## Task brief shape

Use **`templates/recon-brief.md`**. It covers, in order: mode, scope (targets
plus **forbidden** paths), the fixed per-target entry shape, numbered questions
with the load-bearing one marked, stop rules, and the citation rules.

Two parts are easy to omit and expensive to omit:

- **Forbidden paths and skip list**, not just "read-only". `read-only` says what
  the agent may not write; it does not say where it should not waste effort.
- **The stop rule:** *"If the premise of this brief turns out to be materially
  wrong, stop and report it. Do not improvise a substitute task."* Without this,
  a scout facing a wrong premise will quietly answer a nearby question instead,
  and the answer will look like success.

Length caps matter — ask for "under 200 lines". Unbounded reports drift into
summary prose.

### Durable run record

Artifacts under `.pi-subagents/` are gitignored and transient. Keep one durable
record per run under `agent/inventory/`, named `<nn>-<topic>.md`, and note the
run id and model at its top. One file per attempt — do not overwrite a previous
attempt, because comparing two attempts is often what exposes a flaky answer.

## Parallel fan-out

For a survey, group targets into **themed clusters** and run one scout per
cluster with `concurrency` set to the number of clusters. Clusters keep each
report internally comparable and let one bad cluster fail without taking the
others down.

Give every parallel task its own `output` path. Set a generous `timeoutMs`;
recon over many directories is slow, and a timeout mid-report wastes the whole
run.

## What the main session does after every run

1. Read the **short return** first; look specifically for the contradiction line.
2. Open the output file only for the parts that bear on a decision.
3. **Lift decision-relevant content into a repo-owned file** — the artifact is
   transient.
4. **Correct the record where the report falsified something.** Do not quietly
   overwrite; mark the correction and keep the original error visible, because
   the error is usually more instructive than the fix. Example:
   `INSPECT_VS_CHARTER.md` keeps its wrong `:permission`-only finding struck
   through, above the correction.
5. Treat the report as **one level less reliable than a direct read**. It is a
   citation to follow, not a verified fact. Say so when reporting onward.

## Verified capability notes, 2026-07-25

- **Parallel fan-out works well at 3-4 clusters.** Three runs of 4, 3, 3, and 1
  child completed with no rate-limiting and no timeouts at
  `timeoutMs: 1800000`.
- **Adversarial review earns its cost.** A fresh-context reviewer overturned the
  lead session's own draft goal (it had substituted a measurable proxy for the
  actual mission). The lead could not have caught this, having authored the
  draft. Prefer an adversarial brief — *"a review that says looks good is a
  failed review"* — over a neutral one.
- **Scouts misattribute mechanisms while reaching correct conclusions.** Twice
  this session a report's *conclusion* was right and its *cited mechanism* wrong
  (a missing argument blamed instead of dead instance state; a metric called
  non-computable because a counter field was absent while a countable event type
  existed). Spot-check the mechanism, not just the verdict — they fail
  independently.
- **Green commands do not validate the brief.** Verified 2026-07-25: the first
  writer reported `complete`, 74/74 tests, clean typecheck/precommit, and then
  admitted in `RESIDUAL RISK` that required usage telemetry was always
  `not_applicable`. Production never passed its callback, so zero telemetry was
  emitted. Require numbered requirement→file:line→covering-test mapping; any
  unmet or deferred requirement forces `partial`/`scope-blocked`. Independently
  trace production wiring before accepting implementation.

## Open question

**Does `tool_call` fire for tools invoked inside subagent runs?** Undocumented,
and `NOT FOUND` across every repo scanned on 2026-07-25. It matters here
specifically: ground work is delegated, so if hooks do not fire for subagent
tools, delegated work is invisible to any observer this project builds. Settle it
empirically, not by more reading.

## Files in this skill

- `templates/recon-brief.md` — paste-and-fill brief for a delegated recon run
- `templates/recon-report.md` — the mandatory shape of the short recon return
- `templates/implementation-brief.md` — authorization boundary, exact write scope,
  numbered requirements, verification commands, and stop rules for one writer
- `templates/implementation-report.md` — headline-first changed-files,
  behavior, verification, contradiction, and residual-risk return

The recon templates are adapted from `~/dev/daily-workflow-helper/.pi/skills/scva-handoff-orchestrator/`.
Not adopted from it: its `references/runner-usage.md` (documents shell scripts
that do not exist here — this repo uses the `subagent` tool, which supplies
artifact and session paths itself) and its `.d2`/`.svg` flow diagram (five boxes;
see the ASCII flow above). Its `references/run-layout.md` is runner-specific, but
its durability principle was kept — see "Durable run record".

The implementation templates were added on 2026-07-25 at the first writing
delegation, as planned; they are now backed by an actual use rather than
speculative process design.

## Related

- `AGENTS.md` — durable repo rules; points here for delegation.
- `docs/prior-art-inventory.md` — the product of the largest fan-out so far;
  read it as an example of what good delegated output turns into.
