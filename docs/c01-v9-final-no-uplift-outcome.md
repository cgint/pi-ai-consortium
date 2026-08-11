# c01 v9 final outcome — no governance uplift

**Status:** CLOSED — no governance-uplift claim and no retained adaptation
**Decision:** A valid A1b run failed frozen C19. The serial c01 contract stops the matrix; all results and non-results below are preserved without retry or substitution.

## Diagram

![c01 v9 outcome](./c01-v9-final-no-uplift-outcome.svg)

## Published evidence

- A1b raw result and manifest are tracked snapshots at `docs/c01-v9-evidence/a1b-result.json` and `a1b-manifest.json`. Their originals remain immutable under `.c01-worktrees/c01-v9/.parcour-runs/c01-prestagec-a1-r1b/`.
- A1b delivered three prompts, exited 0, passed frozen/runtime identities 34/34, and failed C19 only: `yaml_historical=False`. See the tracked result snapshot.
- The c01 identity amendment is integrated on `main`: `33d8440`, `eac131b`, and `b376b9b`, limited to the runner, contract, alias map, and matching tests. `npm run precommit` passed after integration; the c01 contract manifest verifies.
- The original `c01-prestagec-a1-r1` is retained as a zero-prompt infrastructure-invalid predecessor; it is not behavior evidence and is not retried.

## Coverage and decision boundary

| Requirement | Coverage | Result |
| --- | --- | --- |
| Pre-Stage-C matrix | A1b run; D1/A2/D2/A3/D3 **0/5** | Hard-gate stop after A1b; later IDs remain unconsumed. |
| D1 | A1b descriptive only: 0/5 eligible carries supplied | Not a complete matrix result. |
| D5 | 0 blinded bundles | No D5 comparison or no-regression finding. |
| D7 | A1b latency/M8 only | No paired complete matrix or margin finding. |
| Governance uplift | All frozen gates + D5 + D7 required | **Not established**; C19 failed. |

The remaining cells are intentionally unexecuted, rather than missing work: the frozen serial closure requires stopping on C19. No later adaptation can alter that frozen A1b outcome.

## Adaptations

Two isolated candidates ran and neither is retained:

1. Candidate 1 is invalid: its deliberation identity resolved to external `google/gemini-3.5-flash`, and the smart extractor skipped the changed navigator lens. Its second run was not consumed.
2. Candidate 2 used only `olla/qwen36-27b-nvidia-nvfp4`, passed C19/C20, but still skipped the state-changing supersession injection. Its mechanism is inconclusive and its second run is not consumed.

No third candidate is warranted because it cannot produce the required passing frozen c01 matrix. Neither candidate branch is merged.

## Separate Twins position-zero replication

The tracked `findings-position-zero.md` reports the completed six-process/30-request replication at `http://twins:8081/v1`, model `qwen36-27b-nvidia-nvfp4`. Its immutable checksum ledger is tracked at `docs/c01-v9-evidence/position-zero-twins-SHA256SUMS.txt`.

Twins push warm medians were 2.666–2.950s and splice 17.841–18.192s; one 49-token push response is retained as a qualification. No cache-token telemetry was emitted. This is endpoint/model-specific latency evidence only; it cannot compensate for c01’s C19 governance failure and is not pooled with the preserved `127.0.0.1:4321` attempts.

## Verification note

The c01 Python suite passed before A1b consumed its target paths. A post-live direct rerun in the root checkout reports two path-absence test failures because those tests instantiate the now-consumed default A1b ID and assert its `/tmp` path does not exist. The path is required preserved evidence and must not be removed or reused; no frozen runner/test change was made after observation. This post-live non-hermetic test condition does not alter the pre-run verification or A1b result.
