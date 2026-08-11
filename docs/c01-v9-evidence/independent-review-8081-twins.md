Warning: No models match pattern "olla/qwen36-27b-nvidia-nvfp4"
All 16 tests pass. Now I have all the evidence I need. Let me compile the final adversarial review.

---

# ADVERSARIAL FINAL REVIEW — c01 v9

**Reviewer model:** `claude-opus-4-5` (configured identity of this subagent)  
**Scope:** Read-only analysis of 6 tracked main-repository files + evidence directory  
**Date:** 2026-08-11

---

## HEADLINE

**PASS — no BLOCKER identified.** All seven verification categories hold. The c01 v9 no-uplift stop outcome is truthful, internally consistent, and evidentially supported. One minor NOT FOUND noted (non-blocking).

---

## CONTRADICTS

**None found.** No internal contradiction detected across the six reviewed files, the evidence directory, or the contract manifest. Specifically verified:

| Claim | Verified Against | Result |
|-------|-----------------|--------|
| A1b failed C19 only | `a1b-result.json` L:C19 assertion: `pass=false`, all other 22 assertions `pass=true` | ✅ Consistent |
| 34/34 identity checks passed | `a1b-manifest.json` identity_checks: all 34 `true` | ✅ Consistent |
| Serial stop after A1b | `c01_runner.py` L736: `_preflight()` → L737: `harvest_allowed=True` → L738: `_materialize_workspace()` — no serial matrix logic exists; stop is manual/process-level | ✅ Consistent with narrative |
| No retained adaptations | `outcome.md` Adaptations section + `candidate-1-r1-result.json` (`pass=false`) + `candidate-2-r1-result.json` (`pass=false`, `state_change_injected=false`) | ✅ Consistent |
| Twins separate from c01 | `outcome.md` L41-42: "cannot compensate for c01's C19 governance failure and is not pooled" | ✅ Consistent |
| Original A1 preserved separately | `original-a1-infrastructure-invalid.md`: zero prompts, infrastructure-invalid, run ID consumed | ✅ Consistent |
| Contract manifest rehashed post-A1b | `a1b-manifest.json` pins `contract_sha256=d95916…`; current file hashes to `08168d…`; `outcome.md` Verification Note explains this | ✅ Consistent |

---

## NOT FOUND

| Item | Location Referenced | Actual Location | Severity |
|------|---------------------|-----------------|----------|
| `findings-position-zero.md` | `outcome.md` L41: "tracked `findings-position-zero.md`" | Exists at **repo root** (`findings-position-zero.md`, 4962 bytes), NOT at `docs/c01-v9-evidence/findings-position-zero.md` | ⚠️ Minor — file exists but path reference is imprecise |

This is cosmetic: the file is git-tracked and accessible, just not inside the `docs/c01-v9-evidence/` directory as implied by context. The SHA256SUMS ledger (`docs/c01-v9-evidence/position-zero-twins-SHA256SUMS.txt`) is correctly located.

---

## VERIFICATION SUMMARY

### 1. Original A1 Preserved Separately ✅

- `docs/c01-v9-evidence/original-a1-infrastructure-invalid.md` (3360 bytes) documents `c01-prestagec-a1-r1` as infrastructure-invalid: Pi CLI `0.82.0` expected, `0.82.1` observed, 0 prompts delivered, run ID consumed.
- Alias map (`alias-maps/c01-revision-continuity.json`) contains both `a1-r1` and `a1-r1b` entries for `/tmp` and `/private/tmp` paths.
- Original A1 is never retried or reclassified.

### 2. Pi Exact 0.84.1 and Node v22.23.* Enforced/Recorded ✅

- `c01_runner.py` L81: `C01_PI_VERSION = "0.84.1"`; L82: `C01_NODE_VERSION_PATTERN = r"v22\.23\.\d+"`
- Enforced at preflight: L531 (exact string match for Pi), L532 (regex match for Node)
- Recorded in manifest: `a1b-manifest.json` shows `pi_cli: "0.84.1"`, `node_cli: "v22.23.2"`
- Tests verify: `test_amended_a1_replacement_and_runtime_contract` confirms version enforcement including rejection of `v22.24.0` and `v22.23`

### 3. A1b Valid Runtime Evidence Failed C19 ✅

- `a1b-result.json`: 23 assertions, 22 passed, 1 failed (C19 only)
- C19 failure detail: `yaml_occurrences=1; yaml_historical=False` — the model mentioned "yaml" once but without historical framing words (supersede/replace/history/former/previous)
- Code logic confirmed: `c01_runner.py` L366-367 validates `yaml_historical` requires ALL yaml-mentioning lines to contain at least one historical framing word
- All 34 identity checks passed; process exited cleanly (returncode 0); 3 prompts delivered

### 4. Serial Stop / No-Uplift Is Truthful ✅

- A1b is the only executed cell; D1/A2/D2/A3/D3 are listed as 0/5 in the coverage table
- D5: 0 blinded bundles; D7: incomplete (A1b latency/M8 only)
- No governance uplift claimed; the outcome title explicitly states "no governance uplift"
- Coverage table is honest: marks D1 as "descriptive only", D5 as "0", D7 as "incomplete"

### 5. Current Matching Python Tests and Contract Manifest Verifiable ✅

- **16/16 tests pass** (verified by live execution)
- **12/12 contract files match** their SHA-256 hashes in `c01-contract-files.json`
- Runner SHA-256 matches A1b manifest exactly: `10c05ec6a1b554536c9711b1eb78206e21bba92615ea61334a2b15f856464b59`
- Contract SHA differs from A1b's pinned value (expected: post-A1b test fix rehash, documented in Verification Note)
- All test symbols resolve to runner symbols (verified 17/17)

### 6. Twins Evidence Remains Separate ✅

- `findings-position-zero.md` exists at repo root (4962 bytes)
- `position-zero-twins-SHA256SUMS.txt` tracked at `docs/c01-v9-evidence/`
- Outcome explicitly states Twins "cannot compensate for c01's C19 governance failure and is not pooled"
- No Twins data mixed into c01 result or manifest

### 7. No Candidate Falsely Retained ✅

- Candidate 1: `pass=false`, `C19_fixture=false`, `process_returncode=143` (SIGTERM); described as invalid due to external model identity (`google/gemini-3.5-flash`)
- Candidate 2: `pass=false`, `C19_fixture=true`, `C20_final_text=true`, BUT `state_change_injected=false`; described as mechanism-inconclusive
- Neither branch merged; second run IDs unconsumed; no third candidate warranted
- Authorization record (`hard-gate-stop-and-adaptation-authorizations.md`) documents explicit user authorizations for both

---

## BLOCKER

**None.** No blocking issue identified.

---

## RISK NOTES (Non-blocking Observations)

1. **Contract SHA divergence:** The current `c01-contract-files.json` hashes to `08168d…` while A1b's manifest pins `d95916…`. This is documented and explained (post-A1b test hermeticity fix), but a future auditor unfamiliar with the narrative could flag it. The documentation adequately explains it.

2. **`findings-position-zero.md` location:** Referenced as if inside `docs/c01-v9-evidence/` but lives at repo root. Minor path precision issue; file is accessible and git-tracked.

3. **Candidate 2 passed C19/C20:** While correctly classified as inconclusive (skipped state-changing injection), the fact that an adaptation *could* satisfy C19/C20 is worth noting — it means the frozen c01 fixture check is achievable, just not by the base configuration. This doesn't invalidate the stop; it reinforces that adaptation ≠ frozen matrix compliance.
