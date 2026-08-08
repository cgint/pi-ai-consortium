# Extraction Quality Assessment — 2026-07-31

**Status:** Discovery finding
**Related:** `docs/extraction-analysis-2026-07-31.md` (quantitative metrics)
**Data source:** Spot-check of 4 extraction outputs from 2 sessions + original design doc

---

## 1. Original Design Intent

Source: `~/dev/concepts/pi-ai-consortium/agent/embedded-context-reality-grounded-architecture.md` (Jul 22, 2026)

The original architecture specified **5 vectors**:

| # | Vector | Purpose |
|---|--------|---------|
| 1 | `USER_INTENT_AND_MOTIVE` | Core human objective, stripped of noise |
| 2 | `ACTIVE_CONSTRAINTS_AND_GUARDS` | Session flags (read-only, write-guard, etc.) |
| 3 | `VERIFIED_FACTS_INVENTORY` | Confirmed code facts, file mtimes, test outputs |
| 4 | `EVIDENCE_FRESHNESS_DELTA` | Code mtime vs last test/screenshot timestamp |
| 5 | `CLARITY_AND_AMBIGUITY_SCORE` | CLEAR or AMBIGUOUS with specific missing details |

---

## 2. Schema Drift: 5 → 9 Vectors

| Current Vector | Maps to Original | Notes |
|---------------|-----------------|-------|
| `userRequirements` | ⊂ USER_INTENT | Partial mapping |
| `deliverables` | **NEW** | Not in original design |
| `revisedOrSupersededDirection` | **NEW** | Not in original design |
| `userDecisions` | **NEW** | Not in original design |
| `questionsAndInformationGaps` | ⊂ CLARITY | Lists questions but no overall verdict |
| `controlBoundaries` | ⊂ CONSTRAINTS | Preserved |
| `observedWork` | **NEW** | Not in original design |
| `observedCriticalFacts` | ⊂ VERIFIED_FACTS | Exists but quality differs (see §3) |
| `relevantLearnings` | **NEW** | Not in original design |

**Dropped:** `EVIDENCE_FRESHNESS_DELTA` — the mtime-vs-test-timestamp freshness check. This was the most distinctive vector, designed to catch "code edited but tests not rerun."

---

## 3. Spot-Check Quality (4 extractions, 2 sessions)

### Strengths
- Requirements extraction is accurate and specific
- Control boundaries captured correctly
- Accumulation works — vectors grow richer across turns
- `deliberationNeeded` gating is reasonable

### Weaknesses vs Original Intent

**1. `observedCriticalFacts` is narrative, not factual**

Original: "Confirmed code facts, file mtimes, test outputs, and trace logs."

Actual output:
```
- "Existing filenames show mixed delimiters"
- "The core problem is static depth limiting vs dynamic repository discovery"
```

These are **prose summaries**, not machine-verifiable facts with timestamps, paths, or test output refs. The original wanted structured evidence the probes could mechanically verify.

**2. `relevantLearnings` is interpretive**

No equivalent in original design. Output tends toward the extractor's own analysis ("Legacy data exists with non-standard naming conventions, which may require migration") rather than observed facts.

**3. No evidence freshness**

`EVIDENCE_FRESHNESS_DELTA` was the vector that would have caught staleness — "file X modified at 14:32 but last test run was 13:45." Without it, Contrarian's gate ("compare observed_work against observed_critical_facts") has no temporal signal to detect stale evidence.

**4. No clarity verdict**

Original wanted explicit CLEAR/AMBIGUIOUS state. Current `questionsAndInformationGaps` lists questions but doesn't give an overall clarity assessment. Clarifier probe has no single signal to check.

---

## 4. Assessment

The 9-vector schema **adds breadth but dilutes precision**. The 4 new vectors (`deliverables`, `revisedOrSupersededDirection`, `observedWork`, `relevantLearnings`) provide useful accumulation state but push the extractor toward narrative summarization rather than the tight, verifiable fact extraction the original design intended.

The most impactful loss is `EVIDENCE_FRESHNESS_DELTA` — it was the vector that directly enabled the "stale evidence" detection the architecture was built around.

---

## 5. Unverified

- Whether the drift from 5→9 vectors was intentional design evolution or organic growth during implementation
- Whether the concept repo has a more recent design doc that supersedes the Jul 22 architecture
- Whether probes actually use the missing signals (freshness, clarity verdict) or if they never needed them

---

## 6. Confidence

problem-understanding 90% · info-sufficiency 85% · solution-confidence 60%