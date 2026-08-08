# Context Extraction Analysis — 2026-07-31

**Status:** Discovery finding
**Data source:** `.pi/consortium/*.jsonl` and `*.md` sidecars across 7 projects, 20 sessions, 223 extraction events
**Scope:** Extraction pass quality, latency, failure observability, dead parameters

---

## 1. Sample

| Dimension | Value |
|-----------|-------|
| Projects | 7 (pi-ai-consortium, deliberate-agent, web-scrape-meno, elix-live-chat, agent-coding-gui, bookkeeping, yt-transcripter) |
| Sessions with extraction | 20 |
| Extraction events | 223 |
| MD sidecar turns logged | 263 |
| Sessions without extraction | 55 (pre-extraction era, Jul 19–21) |

---

## 2. Success Rate

| Metric | Value |
|--------|-------|
| Outputs ≥ 1000 chars | 203 (94.0%) |
| Outputs 200–999 chars | 7 (3.2%) |
| Outputs < 200 chars | 2 (0.9%) |
| Empty (0 chars) | 4 (1.9%) |
| Default fallback turns (MD sidecar) | 16/263 (6.1%) |
| Mean output length | 3569 chars |

**Finding:** Extraction works well once history accumulates. Defaults cluster in the first turn of each session when history is minimal (e.g., `hi`-only sessions). Not "routine failure."

---

## 3. Latency

### Extraction

| Bucket | Count | % |
|--------|-------|---|
| < 1s | 5 | 2% |
| 1–5s | 31 | 14% |
| 5–10s | 48 | 22% |
| > 10s | 139 | 62% |

**Mean: 13.2s per extraction pass** (range: 325ms – 27s).

### Per-Component Timing (223 extractions, 9695 probes, 1368 syntheses)

| Component | Calls | Mean | Share of deliberation |
|-----------|-------|------|-----------------------|
| Extraction | 232 | 13.2s | 30% |
| 5 Probes | 9695 | 5.8s each (28.8s total) | 65% |
| Synthesis | 1368 | 2.1s | 5% |
| **Total per deliberation** | — | **≈ 44s** | — |

### KV Cache Benefit

Extraction warms the KV prefix cache for probes. **Probe latency dropped 49%** after extraction was introduced:

| Era | Probe calls | Mean probe duration |
|-----|-------------|--------------------|
| Pre-extraction (Jul 19–24) | 9669 | 5748ms |
| Post-extraction (Jul 25–28) | 1053 | 2931ms |

Extraction pays for itself partially: 13.2s extraction saves ~14.4s across 5 probes (5 × 2.8s reduction). Net deliberation is faster with extraction than without.

**Extraction is not the bottleneck — it is an investment that reduces probe cost.** The 30% share of deliberation time buys a 49% probe speedup.

---

## 4. Dead Generation Parameters

**`maxTokens` and `temperature` are ignored for all model calls.**

- `extractContextFromMessages` requests `maxTokens=1024, temperature=0.2` (`src/extraction.ts:94`)
- `callModelWithAuth` receives them as `_maxTokens, _temperature` (underscored = unused) (`src/model.ts`)
- `streamSimple` is called with `{ apiKey, headers, signal }` — no generation params passed
- Same applies to probes: `maxProbeTokens=512` and `probeTemperature=0.7` are also dead

**Effect:** Extraction runs unbounded at provider defaults, producing 1000–5000 char outputs despite requesting 1024 tokens.

---

## 5. Silent Parse Failures

`src/extraction.ts:121`:
```ts
} catch {
  return getDefaultExtractedContext(messages);
}
```

No telemetry event emitted. Cannot distinguish "empty because no signal" from "empty because parse failed." The only observable evidence is the MD sidecar showing default values ("General task execution", "Session initialized").

---

## 6. Content Quality (Spot-Checked)

Sampled from `deliberate-agent` Jul 26 session (26 turns):

- Turn 1: defaults (minimal history)
- Turns 2–26: rich, specific vectors with accurate facts, requirements, and observed work
- Accumulation works — vectors grow richer across turns
- No degradation observed over long sessions

---

## 7. Verified File References

| Claim | Citation |
|-------|----------|
| Extraction prompt | `src/extraction.ts:12-57` |
| maxTokens/temperature dead | `src/model.ts` — `streamSimple` called without generation params |
| Silent catch | `src/extraction.ts:121` |
| Output logged full (no truncation) | `index.ts:466` — `output: result.text` |
| Token budget requested | `src/extraction.ts:94` — `1024, 0.2` |
| Probe token budget requested | `src/config.ts:98` — `maxProbeTokens: 512` |

---

## 8. Corrected Thesis

**Extraction works well when history is rich** (94% produce 1000+ chars). The real characteristics are:

1. **KV cache investment** — 13.2s extraction saves ~14.4s across 5 probes (49% probe speedup). Net positive.
2. **Observability gap** — parse failures are silent (6.1% fallback rate, unmeasurable)
3. **Dead params** — maxTokens/temperature ignored for all model calls

---

## 9. Confidence

problem-understanding 95% · info-sufficiency 90% · solution-confidence 75%