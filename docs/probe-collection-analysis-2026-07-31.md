# Probe Collection Analysis — 2026-07-31

**Status:** Discovery finding
**Data source:** `.pi/consortium/` local logs (25 session files, 1677 probe invocations across 337 deliberations)
**Scope:** Per-probe contribution rates, format compliance, injection outcomes, gap assessment

---

## 1. Per-Probe Contribution Rates (Verified)

Derived from `probe_complete` events in `.pi/consortium/*.jsonl`. 1677 probe invocations across 337 deliberations (5 probes each).

| Role         | Calls | NC    | INFO | WARN | BLOCK | Format Fail | Contribution Rate |
|-------------|-------|-------|------|------|-------|-------------|-------------------|
| **Architect**   | 336   | 161   | 60   | 74   | 25    | 16          | **52%**           |
| **Clarifier**   | 336   | 175   | 49   | 84   | 18    | 10          | **48%**           |
| **Contrarian**  | 335   | 201   | 39   | 68   | 23    | 4           | **40%**           |
| **Navigator**   | 335   | 205   | 45   | 64   | 15    | 6           | **39%**           |
| **Responder**   | 335   | 232   | 52   | 38    | 6     | 7           | **31%**           |
| **Total**       | 1677  | 974   | 245  | 328  | 87    | 43          | **42%**           |

**Key finding:** Responder is the quietest probe (31% contribution, 69% NC). Architect is the loudest (52% contribution). Earlier session-level analysis that attributed specific capabilities to specific roles was unverified — session JSONL only logs `synthesis` text, not per-probe outputs. This table is the first role-attributed evidence.

### Contributing Probes Per Deliberation

| Contributors | Deliberations | % of 337 |
|------------:|-------------:|---------:|
| 0 (all NC)  | 72           | 21%      |
| 1           | 75           | 22%      |
| 2           | 62           | 18%      |
| 3           | 49           | 15%      |
| 4           | 38           | 11%      |
| 5 (all fire)| 41           | 12%      |

21% all-NC rate is reasonable. 12% where all 5 probes fire simultaneously raises noise concerns.

---

## 2. Format Compliance Issues

157 probe outputs failed `validateProbeOutput` coercion in `src/core.ts` (line ~20). Breakdown:

| Failure Type       | Count | Cause |
|-------------------|-------|-------|
| **`TAG ` + severity (recoverable)** | 114 | Model writes `TAG INFO ...` / `TAG WARN ...` / `TAG BLOCK ...` — regex `/^(INFO|WARN|BLOCK)\s+\S/` does not match. **Fully recoverable** by stripping leading `TAG `. Distribution: Architect 26, Clarifier 22, Contrarian 28, Navigator 25, Responder 16. |
| **`TAG ` bare (unrecoverable)** | 3 | Model writes `TAG ` without severity tag (e.g. `TAG The timeout test...`, `TAG NO_CONTRIBUTION`). Cannot be recovered. |
| Empty output        | 23    | Model returned empty string |
| Other invalid       | 7     | Conversational responses, emoji bullets, etc. |
| Synthesis invalid   | 160   | Synthesis model ignores tag format (expected — synthesis has different prompt) |

**Impact:** 114 recoverable outputs are real probe contributions silently coerced to NO_CONTRIBUTION at runtime. The 42% contribution rate in Section 1 is a **potential** rate (measured with lenient parsing). **Delivered** rate is lower — approximately (703-114)/1677 ≈ 35%. The 7-point gap between potential and delivered is the parser fix's expected gain.

---

## 3. Injection Outcomes

| Outcome               | Count |
|-----------------------|-------|
| `injection_complete`  | 235   |
| `injection_skipped`   | 103   |
| `synthesis_complete`  | 91    |
| `deliberation_failed` | 1     |

- 235 - 91 = **144 injections without synthesis** (probes contributed but synthesis was bypassed — likely all-NC after validation coercion)
- 103 skipped: 100 were `NO_CONTRIBUTION` from extraction pass, 3 were greetings
- 342 deliberation_start - 235 - 103 - 1 = **3 unaccounted** (likely timeouts or aborts)

---

## 4. Classification of Proposed New Probes by Layer

Three candidate probes were discussed. Classified against the contract in `src/config.ts` (`PROBE_SYSTEM_PROMPT`) and `src/core.ts` (`validateProbeOutput`):

### 4a. Grounding-Seeker — **FITS current contract**

> "Asserted X without reading it", "guessed instead of searching"

This observes **past-fact violations** (claims made without evidence in `observed_critical_facts`). Compatible with `PROBE_SYSTEM_PROMPT`'s "OBSERVED PAST REALITY ONLY" directive. Could be added as a 6th probe or folded into an existing `roleLens`.

**Layer:** Probe layer (roleLens addition)
**Risk:** Low — stays within existing contract

### 4b. Best-Practice-Seeker — **VIOLATES current contract**

> Suggests architectural improvements, coding standards, design patterns

This is **prescriptive and future-facing** ("you should structure it this way"). Directly conflicts with `PROBE_SYSTEM_PROMPT`'s "do NOT speculate on what the agent 'might' or 'should' do". Output would likely be coerced to NO_CONTRIBUTION by `validateProbeOutput`.

**Layer:** Synthesis/injection layer (not a probe)
**Risk:** High — would require either (a) a second probe class with its own system prompt (breaks KV-prefix-cache rationale in `src/types.ts:ProbeConfig`), or (b) folding into synthesis prompt

### 4c. Plan-Decomposer / Structurizer — **VIOLATES current contract**

> Breaks tasks into steps, suggests execution order

Also **prescriptive and future-facing**. Same contract violation as Best-Practice-Seeker.

**Layer:** Synthesis/injection layer (not a probe)
**Risk:** High — same KV-prefix-cache tradeoff

---

## 5. Preregistration Freeze Conflict

**`docs/behavioral-parcour-roadmap.md`** (concept repo) states:
- Preregistration v7 is frozen (`docs/behavioral-preregistration-2026-07-30.md`)
- Goal `ms0hmpjw-uqk5bb` confirmed
- Batch paused awaiting user decision on runtime amendment
- "No stage may be silently resized, reordered, or repaired after observation"

**Changing probe composition mid-parcour invalidates comparability** with any frozen baseline. Any probe addition must be surfaced as a preregistration amendment, not a silent config change.

---

## 6. Assessment: Is the Collection "Good"?

### Strengths
- 100% unique syntheses across 109 deliberations examined (no repetition)
- 21% all-NC rate is reasonable (probes are selective, not noisy)
- Roles cover distinct axes: boundaries (Architect), ambiguities (Clarifier), verification (Contrarian), goals (Navigator), errors (Responder)
- Responder's 31% contribution rate suggests good selectivity — it only fires on real tool failures

### Weaknesses
- **Silent signal loss:** 117 bare-TAG outputs coerced to NO_CONTRIBUTION (format compliance bug, not a probe quality issue)
- **No grounding probe:** Nothing systematically checks "did the agent verify this claim before asserting it?" — the session evidence shows agents regularly asserting facts without evidence (collision counts, listing sizes, file existence)
- **Responder is underutilized:** 69% NC rate — its gate ("audit past tool calls for errors") may be too narrow. Many tool failures are caught by other probes' broader lenses
- **No performance/latency lens:** Performance regressions caught incidentally, not by a dedicated probe
- **BLOCK saturation in complex sessions:** deliberate-agent session showed 54% BLOCK rate — 5 probes firing BLOCK simultaneously may overwhelm the agent rather than guide it

### Recommendation (not execution)
Cheapest first test: add grounding language to an existing `roleLens` (e.g., Contrarian or Clarifier) rather than adding a 6th probe. This avoids the preregistration freeze conflict and the KV-prefix-cache tradeoff. The format compliance fix (accepting `TAG ` prefix) is a separate low-risk code fix.

---

## 7. Citations

- `src/config.ts` — `PROBE_SYSTEM_PROMPT` (line ~12), probe definitions (line ~48)
- `src/core.ts` — `validateProbeOutput` regex (line ~24)
- `src/types.ts` — `ProbeConfig` interface (line ~43), KV-prefix-cache comment
- `.pi/consortium/*.jsonl` — 25 session log files, 1677 probe_complete events
- `docs/behavioral-parcour-roadmap.md` — preregistration freeze status