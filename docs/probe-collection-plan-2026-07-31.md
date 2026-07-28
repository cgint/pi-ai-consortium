# Probe Collection Improvement Plan

**Status:** Draft — Step 1 ready, Steps 2-4 sequential
**Analysis:** `docs/probe-collection-analysis-2026-07-31.md`
**Evidence:** `agent/probe_evidence.txt` (Step 0 read-only dump)

---

## Goal

Make the consortium more helpful: recover discarded signals, add grounding checks, and reduce redundancy. Measure each change incrementally.

---

## Evidence (Step 0 — read-only, complete)

### Responder's 6 BLOCKs — HIGH VALUE, not weak
All 6 catch **agent drift** (exploring wrong files, re-reading already-answered questions, analysis paralysis). This is not tool-error detection — it's **goal-tracking**. Responder is the only probe that catches "you're working on the wrong thing." **Do not retire.**

### Responder's 35 WARNs — same pattern
Most catch agent drift, malformed tool calls, and unanswered user questions. Complements the BLOCKs. Selective but high-signal.

### TAG prefix outputs — 114 recoverable, 3 unrecoverable
114 probe outputs start with `TAG INFO ...` / `TAG WARN ...` / `TAG BLOCK ...`. The regex in `src/core.ts` does not match these — they are coerced to NO_CONTRIBUTION at runtime. **Fully recoverable** by stripping the leading `TAG `. 3 outputs start with bare `TAG ` (no severity) — unrecoverable.

**Distribution:** Architect 26, Clarifier 22, Contrarian 28, Navigator 25, Responder 16. Every probe affected — not a single-role issue.

### All-5-fire deliberations — evidence inconclusive (5/41 sampled)
Sample of 5 shows probes echoing the same observation. 41 deliberations with all 5 firing — but sample is non-random (first 5 chronologically, likely same session/topic). **Cannot conclude "mostly redundant" from 5/41 biased sample.** Needs full dump before tightening gates.

---

## Revised Plan (4 steps)

### Step 1 — Parser Fix: Recover 114 Discarded Outputs (signal recovery)

**What:** Strip leading `TAG ` in `validateProbeOutput` before applying the existing regex. `TAG INFO x` → `INFO x`.

**Why:** 114 valid probe observations silently discarded at runtime. Every probe affected (Architect 26, Contrarian 28, Navigator 25, Clarifier 22, Responder 16). Cheap fix, no behavior change beyond accepting valid output.

**Files:** `src/core.ts` (parser), `test/core.test.ts` (red-green tests)

### Step 2 — Emit Role in Telemetry (measurement)

**What:** `probe_start` / `probe_complete` events include explicit `role` field.

**Why:** Per-role contribution rates are inferred from index position. Breaks silently if probes are reordered. Prerequisite for measuring any composition change.

**Files:** `index.ts` (telemetry emission), `src/types.ts` (type update)

### Step 3 — Add Grounding to Contrarian (critical thinking)

**What:** Expand Contrarian's `roleLens` to include grounding: "asserted X without verifying", "claimed file/content exists without checking". Define "more critical thinking" operationally as **contradiction detection**: observedWork vs userDecisions/userRequirements.

**Why:** Session evidence shows agents regularly assert facts without evidence (collision counts, listing sizes). Contrarian already owns "work vs verified facts" — grounding is the natural extension.

**Files:** `src/config.ts` (roleLens text only)

### Step 4 — Reduce Redundancy (signal quality)

**What:** Tighten probe gates to reduce all-5-fire rate. **Blocked** — need full dump of all 41 all-5-fire deliberations before deciding which gates to narrow.

**Files:** `src/config.ts` (roleLens text)

**⚠ Blocked:** Must re-measure after Step 1 (parser fix raises contribution rates). Do not tune gates against stale numbers.

---

## Deferred (open questions)

- **Structured synthesis:** 40-word constraint exists for a reason. Multi-probe summaries may violate "nudge not lecture." Revisit after redundancy reduced.
- **Extraction pass improvement:** Better context vectors feed better probe decisions. Separate investigation — not in scope.
- **Responder retirement:** Evidence shows Responder catches high-value agent drift. Keeping it.

---

## Dependencies

```
Step 1 (parser fix)  ──→ independent, cheap win
Step 2 (telemetry)   ──→ independent, infrastructure
Step 3 (grounding)   ──→ independent, behavior change (measure after)
Step 4 (redundancy)  ──→ BLOCKED until Step 1 re-measurement + full all-5-fire dump
```

---

## Constraints

- `PROBE_SYSTEM_PROMPT` unchanged (KV-prefix cache preserved)
- N=5 maintained (no latency increase in serial mode)
- Post-Step-1 numbers not comparable to 42% baseline (parser recovers 114 outputs)
- Sample bias: most `.pi/consortium/` logs are consortium-on-consortium sessions