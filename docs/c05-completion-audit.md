# c05 independent completion audit

**Verdict:** `<disapproved/>` — protocol-blocked closure is valid, but the original behavioral objective is not achieved.

**Independent auditor:** Herdr read-only worker `c05-completion-audit`

**Raw audit session:** `docs/c05-evidence/c05-completion-audit-session.jsonl`

**SHA-256:** `f6f802c5c7466f8576d3dc11bcfbe4c2e693e28108a30626562a823568bdbef2`

## Requirement map

| # | Requirement | Status | Evidence |
|---:|---|---|---|
| 1 | Preserve c01–c04; fresh c05 only | Pass | No c01–c04 path changed after c04 closure; `docs/c05-supersession-preregistration.md` |
| 2 | Preserve Phase 0 attempt 1; retain accepted attempt B | Pass | `docs/c05-evidence/phase0-capability/`; `phase0-capability-b/` |
| 3 | Phase 0 compatibility evidence | Pass | `phase0-capability-b/result.json`; independent audit; frozen verifier |
| 4 | Pi 0.84.* / Node 22.* patch policy with strict gates | Pass | `scripts/behavioral-parcour/c05_runner.py`; compatibility probe; verifier/tests |
| 5 | Deterministic causal-failure reproduction | Pass | `test/core.test.ts`; causal-fix history |
| 6 | Minimal general causal fix | Pass | `src/core.ts`; `test/core.test.ts`; `test/injection-order.test.ts` |
| 7 | c05-only scorer correction | Pass | `c05_scorer.py`; `test_c05_scorer.py`; corpus parity verifier |
| 8 | Format-valid attempt-6 PASS authorizes preflight | **Blocked** | `independent-review-attempt-6-format-invalid.md`; no valid review for `56f51c8` |
| 9 | Fresh 8-cell smoke | **Blocked** | 8/8 smoke ledger records remain unconsumed; no smoke raw evidence |
| 10 | Ordered 48-cell matrix | **Blocked** | 48/48 matrix records remain unconsumed; smoke transition absent |
| 11 | Bounded uplift | **Blocked** | No behavioral cells; continuity/mechanism/control values are N/A |
| 12 | Honest result and guard recommendation | Pass — blocked branch | `docs/c05-final-protocol-blocked-outcome.md`; guard retained default-off |
| 13 | Independent completion audit | Pass | This audit and raw independent session |

## Mechanical verification

The auditor executed the frozen verifier against `56f51c879ebb60526db1e2f4d7044272279f7d46` and confirmed:

- 36 contracted files match current and frozen bytes;
- 56 ledger records are unconsumed;
- 56 raw directories contain only empty `.gitkeep` files;
- no scheduled behavioral runtime root exists;
- corpus parity permits only the authorized separator metadata;
- Pi `0.84.2` compatibility evidence contains two `get_state` controls, zero prompts, valid exact model identity, and 13/13 checks.

## Missing deliverables

1. No format-valid session-backed PASS for replacement freeze `56f51c8`.
2. No authorized post-freeze preflight.
3. No smoke raw evidence or smoke decision.
4. No matrix raw evidence or paired mechanism/continuity/control/latency/tool-call results.
5. No bounded-uplift result.

Attempt 6’s substantive PASS does not satisfy its explicit first-byte format gate. The active protocol requires stop, protocol-blocked closure, zero behavioral claims, and no attempt 7. Therefore the goal must not be marked complete.

<disapproved/>
