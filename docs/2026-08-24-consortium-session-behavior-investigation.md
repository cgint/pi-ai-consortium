# Consortium session-behavior investigation

**Started:** 2026-08-24  
**Status:** Active — append-only evidence log; consolidate only after comparative review.  
**Scope:** Session records under `~/.pi/profiles/partner/agent/sessions/` and `~/.pi/agent/sessions/`, restricted to files modified within the preceding 14 days.

## Problem statement

`pi-ai-consortium` is intended to help agents orient, preserve user boundaries, and surface evidence-based risks without disturbing the human-agent collaboration. A reported session showed the opposite: Consortium asserted a false tool-output truncation and injected a directive to clarify before proceeding during explicit strict-discuss/read-only mode.

This investigation will compare persisted Consortium deliberations across recent sessions and models. It will establish: when deliberations ran, what they said, whether their claims were supported by the corresponding session evidence, and whether behavior differed by provider/model. Raw session content is not copied here; this log records concise findings and source paths.

## Confirmed incident

- **Primary session:** `/Users/cgint/.pi/profiles/partner/agent/sessions/--Users-cgint-dev-external-pi-olla-autodetect--/2026-08-24T14-39-12-286Z_01a03436-0b9e-7a21-aa24-b775e5965f31.jsonl`
- **Session model:** `olla/deepseek-v4-flash-dspark` (from the session record).
- **Mode:** explicit `discuss-mode: read` / strict-discuss read-only.
- **Persisted deliberation, 14:41:48:** claimed that `src/extension.ts` read output “was truncated by 7,736 characters.”
- **Contradictory session evidence:** the immediately preceding `read` of `/Users/cgint/dev-external/pi-olla-autodetect/src/extension.ts` returned 9,690 characters and contained no truncation marker.
- **Implementation cause:** `src/context.ts` applies `formatAgentMessageContent(message, 2000)` to every history message before both extraction and probes. For the 9,690-character result, it retains 1,954 characters and inserts its own `[truncated 7736 characters]` marker. The probe mistook this internal compaction for tool-output truncation.
- **Persisted deliberation, 14:43:40:** “Clarify the specific model types needing adaptation and whether LiteLLM will replace or coexist alongside the Olla proxy before proceeding.” This is directive/gating language despite the active strict-discuss read-only boundary.
- **Injection path:** `index.ts` injects a non-`NO_CONTRIBUTION` synthesis as a synthetic `role: "user"` message. See `index.ts` context handler and `src/context.ts` history formatting.

## Initial contract gap

Expected: probes receive the full history plus Extracted Strategic Context, or explicitly know when a representation is compacted and must not infer an underlying tool failure.

Actual: all history entries are retained, but every individual message is capped at 2,000 characters before Pass 1 extraction and Pass 2 probes; Extracted Strategic Context is derived from the same capped representation.

## Scope inventory

- 2026-08-24: 286 matching partner-profile session JSONLs and 80 matching global-agent session JSONLs were found using `find ... -mtime -14`.
- Next: identify only records with persisted `customType: "pi-ai-consortium"`, then group those by provider/model and inspect concise evidence around each deliberation.

## Open questions

- How often did internal compaction cause unsupported claims?
- Does directive or user-channel-authoritative synthesis vary by model/provider?
- Are there successful/no-contribution cases that identify a safe behavioral baseline?
- Does the context-event lifecycle produce repeated deliberations within one human turn?

## Investigation log

- 2026-08-24: Reduced the 366 recent session records to 29 records containing persisted `customType: "pi-ai-consortium"` deliberations. Model identity is available from each session's `model_change` records. Next step: aggregate metadata first; inspect transcript context only for representative or anomalous findings.
- 2026-08-24: Methodology fixed before corpus review. Extract one metadata row per session and per deliberation, attributing each event to the active `model_change` at that point. Measure actual message content above the 2,000-character compaction threshold, truncation-language and directive-language flags in syntheses, strict-discuss/read-only state, and event positions. Treat model differences as anecdotal unless the same flag appears in at least two independent sessions for one model and an exposed comparator model lacks it. Read transcript content only in a bounded window for flagged records.
- 2026-08-24: **Correction:** the initial metadata run filtered by filesystem modification time and included at least one August 6 session, outside the requested two-week period. Its aggregate values are discarded. The extractor will instead filter by each session record's own start timestamp.
- 2026-08-24: Corrected metadata scope: 26 sessions and 98 persisted deliberations across 12 provider/model cohorts. Truncation language occurs in five cohorts (`8081-twins/qwen36-27b-nvidia-nvfp4`, `olla/deepseek-v4-flash-dspark`, `olla/qwen36-27b-nvidia-nvfp4`, `olla/qwen38-27b-ud-q4-xl-mtp-ngram`, `openai-codex/gpt-5.6-luna`, and `openai-codex/gpt-5.6-terra`; the list contains six cohorts—corrected count: six). Directive-language flags while strict read-only is active occur in six cohorts. **Hypothesis:** these are design-wide failure modes, not yet model-specific effects; task mix and exact synthesis semantics remain confounders. Next: bounded verification of representative flagged events.
- 2026-08-24: **Correction:** the definitive truncation-language count is six cohorts, listed in the preceding entry; its initial “five” is a typo.
- 2026-08-24: Read only the persisted synthesis strings for one or more truncation events in each of the six cohorts. All made concrete statements that outputs/files were truncated; several directed the agent to narrow searches, re-read files, verify artifacts, or retry edits. This establishes repeated *assertion* across providers/models, not that each assertion is false. Representative source pointers: `2026-08-11T20-37-31-653Z_019ff28b-6d85-7629-b378-370ec49a6807.jsonl`, `2026-08-24T14-39-12-286Z_01a03436-0b9e-7a21-aa24-b775e5965f31.jsonl`, `2026-08-11T18-56-19-406Z_019ff22e-c5ce-76e6-b16e-58ae42feba90.jsonl`, `2026-08-21T10-11-49-035Z_01a023ce-2aab-79f2-8874-c01b18302913.jsonl`, `2026-08-11T20-14-44-543Z_019ff276-913f-742d-ab1b-c45df8ac98e5.jsonl`, and `2026-08-14T11-09-53-180Z_019ffff6-d09c-72f7-ba90-ee43b64019f6.jsonl` under the configured session roots. Next: compare each claim with adjacent recorded tool-result metadata.
- 2026-08-24: Bounded metadata verification of six representative claims: five had an immediately preceding successful tool result with no recorded `[truncated …]` marker; the sixth (`olla/qwen38-27b-ud-q4-xl-mtp-ngram`, web-scrape session line 209) followed a real failed `edit`, so it remains unclassified until its short error text is compared with the synthesis. This metadata alone does not prove target-to-claim correspondence for the five general claims. The Olla DeepSeek incident remains the only exact, verified false inference.
- 2026-08-24: Resolved the Qwen38 exception: its preceding `edit` result explicitly says that the response hit the output-token limit and its arguments may be truncated. The related Consortium warning was therefore supported. This confirms that the system can surface a valid tool-output warning; the defect is not the word “truncated” itself, but treating unlabelled internal compaction as equivalent evidence.
- 2026-08-24: Boundary-retention check: Extracted Strategic Context represents strict-read-only boundaries inconsistently. It correctly retained explicit read-only language in the DeepSeek, Gemini, Olla-Qwen dflash2, and Wafer samples. In two other sessions whose session-level `discuss-mode` was read-only, the sampled extracted `controlBoundaries` retained only unrelated scope rules (respectively, do not touch `.pi/consortium/`, and preflight/code-commit scope). **Verified:** extraction can omit the active read-only boundary; **unverified:** whether that omission caused any particular directive synthesis.

## Current status

- Corpus discovery and metadata-first comparison are complete for the requested two-week window: 26 sessions, 98 persisted deliberations, 12 provider/model cohorts.
- Verified design defects: per-message 2,000-character history compaction is presented to both extraction and probes without provenance; one Olla DeepSeek synthesis falsely treated its resulting marker as a truncated successful `read`; synthesis is injected as `role: "user"` by `index.ts`.
- Verified counterexample: one Olla Qwen38 warning accurately reflected a recorded output-token-limit `edit` failure.
- Comparative conclusion is intentionally pending. Current data supports a **design-wide risk hypothesis**, not a ranking of models: cohorts have unequal task mixes and different numbers of deliberations.
- Continue from the flagged session pointers above by verifying target-to-claim correspondence in bounded transcript windows and separately sampling directive syntheses under retained versus omitted read-only boundaries.

## Proposed improvement directions (not approved for implementation)

1. **Restore history parity:** pass full message content to both extraction and probes, plus Extracted Strategic Context. If a hard token limit requires compaction, preserve a machine-readable distinction between *internal context compaction* and an actual tool result; internal compaction must never be evidence of tool truncation.
2. **Evidence-gate the Responder:** allow a tool-failure/truncation finding only when the original tool record explicitly carries an error or truncation marker. Otherwise return `NO_CONTRIBUTION`.
3. **Make session boundaries deterministic:** supply strict-discuss/read-only state directly to the governor and injection policy; do not depend on LLM extraction retaining it. In that state, suppress directive/gating contributions.
4. **Remove user-like authority:** do not inject synthesis as a synthetic `role: "user"`. Use a lower-authority, clearly attributed mechanism and reject directives, unsupported factual claims, and unstructured output before delivery.
5. **Add trace-derived regression tests:** cover the 9,690-character successful `read` case, the genuine output-token-limit `edit` case, read-only boundary omission, and one contribution maximum per human turn (the last remains unverified as a runtime defect).

## Architectural reframing

The preceding directions are containment, not the core redesign. The verified failure is that a lossy, model-interpreted transcript is allowed to become an authoritative governance message.

A core design must separate three things that are currently collapsed:

```text
immutable session evidence ──> evidence-linked findings ──> policy decision
     (full history)              (claim + source IDs)        (surface / suppress)
```

- Models may propose a finding, but it is valid only if it cites immutable session evidence (message/tool-result IDs) and labels uncertainty.
- Deterministic policy owns mode/boundary enforcement and whether a finding is surfaced; models do not issue commands or control workflow.
- The agent receives an attributed advisory finding, not synthetic user input. No evidence citation or policy permission means `NO_CONTRIBUTION`.

This makes Consortium an evidence-backed pre-execution governor rather than a second agent speaking through the user channel.

### Correction: core product invariant

The preceding “out-of-band observation” framing is rejected: it would avoid disturbance by removing the intended support. The core invariant is instead **silence unless there is a valid, helpful, non-obvious contribution**.

A contribution is valid only when it is simultaneously:

1. grounded in full session evidence;
2. new relative to what the agent already has in the history and current Strategic Context;
3. materially useful to the immediate next step; and
4. supportive of the active mode and user boundary.

If any condition fails, the correct output is `NO_CONTRIBUTION`. This is not a post-hoc validator layer; it is the semantic contract the probes and synthesis must optimize for. Full-history parity is the prerequisite because validity and novelty cannot be judged from a lossy record.

### C1–C4 deliberation contract

```text
full history ─> C1/C2: one extraction pass ─> C3: probes ─> C4: consolidate
                 C1: extract lens            full history     only if >0
                 C2: reason whether          + lens              contributions
                     deliberationNeeded
                     is true or false
```

- **C1 — Extraction responsibility:** within the single full-history extraction call, filters noise and fog into key points, active boundaries, important evidence, and possible gaps. It is an index/lens, not a factual authority or substitute for history.
- **C2 — Necessity-reasoning responsibility:** within that same extraction call, reasons whether the returned `deliberationNeeded` boolean should be `true` or `false`. `false` means no probe work; `true` is admission to inspect, not permission to contribute. The later deterministic governor applies cadence and guards to route execution; it is not C2.
- **C3 — Probes:** receive the complete original history plus the C1 lens. The lens directs attention; original history decides truth. Each probe independently decides whether to stay silent and returns a contribution only when it is grounded, novel, immediately useful, and supportive; otherwise it returns `NO_CONTRIBUTION`, even after C2 opened the probe stage.
- **C4 — Consolidation:** runs only when at least one probe contributes. It removes duplicates and produces the smallest supportive contribution; it cannot introduce a new claim.
- A disagreement resolves toward the original history, never toward C1 extraction or C4 consolidation.

## Review of external implementation advice (2026-08-24)

**Accepted core:** repair history representation before prompt work. The verified DeepSeek failure arose from an ambiguous Consortium-generated truncation marker, so asking a model to compensate for it would not repair the cause. Add a red test covering the 9,690-character successful `read`, then restore C1/C3 full-history parity. Measure payload size and stop for a design decision if this breaches configured timeouts; do not silently reintroduce lossy compaction.

**Aligned with C1–C4:** C2-false must result in zero probe calls; every C3 probe still independently returns `NO_CONTRIBUTION` unless it has a grounded, novel, immediately useful, supportive contribution; C4 runs only for non-zero contributions and must not introduce claims absent from them.

**Defer/reframe:** regex-based imperative rejection is a useful defense-in-depth experiment, not the core behavioral solution; it risks suppressing legitimate supportive wording and cannot establish groundedness or novelty. Likewise, DSPy/GEPA is premature until a small, user-approved, redacted trace fixture set and deterministic C1–C4 regressions exist. Prompt changes should follow the honest representation and express C3 silence/support semantics, not attempt to compensate for bad input.

**Separate scope:** synthetic `role: "user"` injection and deterministic read-only enforcement are real, separately verified issues, but are not part of the full-history/C1–C4 repair unless explicitly brought into scope. Private-session fixtures require redaction and approval before they are committed.

### Delivery contract correction

C4 is not a user-facing review surface. When—and only when—C3 produces one or more valid contributions, C4 must consolidate them and deliver that result automatically to the **agent’s working context**. The user must not inspect, relay, or babysit the deliberation. Delivery mechanism is secondary to this invariant: `0` contributions means no added context; `>0` contributions means the agent receives the smallest grounded, helpful, supportive consolidated input. Full-history parity is the principal lever because C1 extraction, C2 necessity, C3 silence/contribution, and C4 consolidation all depend on accurate shared evidence.

### Human-input emphasis correction

Do not rely on C1 extraction alone to preserve user wording or emphasis. In addition to complete chronological history and the extracted lens, C3 needs a focused human-input emphasis block at the end of its context. Repeating every human turn would recreate transcript noise and could re-emphasize superseded instructions, so the refined design is an **Active User Direction Pack**:

1. original human mandate — always present;
2. current human turn — always present;
3. its immediate clarification/correction chain — when relevant;
4. active durable decisions and constraints — C1 selects source message IDs;
5. superseded directions — referenced briefly rather than re-emphasized.

Selection and rendering must be separated: C1 may identify relevant source IDs, but deterministic code retrieves exact text or clearly labelled exact excerpts from the original human records. The original and current slots cannot be dropped by C1. The full history remains the source of truth; this pack is only a top-of-mind focus aid. Genuine human provenance must be captured explicitly—`role: "user"` alone is insufficient because historic Consortium injections use that role. Synthetic deliberations must never enter the pack.

## Implementation slice — 2026-08-24

Implemented and focused-tested:

- C1/C3 historical rendering no longer applies the 2,000-character cap; the 9,690-character successful-read regression now passes in both paths.
- Genuine human turns receive deterministic `human-N` source IDs; historic `[CONSORTIUM DELIBERATION]` user-role records are excluded from the direction pack.
- C1 may select active/superseded source IDs; C3 receives original and current genuine human input plus selected active inputs after its role lens.
- C1’s C2 instruction now requires a concrete signal; C3 independently owns `NO_CONTRIBUTION`; C4 is instructed not to introduce claims absent from probe contributions.

**Measured blocker:** metadata over the requested two-week corpus reports median raw message content of 172,970 characters, p95 of 700,646, and maximum 3,413,216 (before XML framing and direction-pack duplication). This makes unrestricted full-history delivery an explicit context-budget decision, not a safe assumption. No hidden replacement cap was introduced. Keep this slice uncommitted pending a user decision on the full-history budget/strategy.

### Decision and completed trial slice — 2026-08-24

The user chose to try uncapped full history rather than design an overflow architecture from whole-session raw-character estimates. Those estimates are retained as risk context but do not demonstrate per-deliberation token overflow or runtime failure.

Final slice:

- C1 and C3 share complete, uncapped historical message content.
- Known historic Consortium injections are attributed as `[CONSORTIUM]`, never as genuine human turns.
- C1 ends with exact original/current genuine-human focus; C3 ends with an Active User Direction Pack after each role lens.
- Single-turn input is marked original-and-current; stale per-turn `human-N` selections are excluded from accumulated baselines; the current human input cannot inherit superseded status.
- Any remaining optional compaction helper emits a self-attributed Consortium omission note, never the ambiguous `[truncated …]` marker.
- Deliberation results and logs record the exact largest rendered C3 payload character count for runtime evaluation.
- C2-false still skips probes; each C3 probe independently owns `NO_CONTRIBUTION`; C4 is skipped at zero contributions and remains automatically delivered to the agent otherwise.

Verification: focused red-green regressions added. Final `npm run precommit` passed on 2026-08-24: TypeScript clean, 55 test files / 491 tests passed, and `npm audit --omit=dev --audit-level=moderate` reported zero vulnerabilities. **Unverified:** behavior with real configured models, including context limits and timeouts; evaluate in a new live session using persisted `probe_payload_chars` and error records.
