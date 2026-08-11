# C01 A1 infrastructure failure — Pi CLI identity drift

**Status:** INFRASTRUCTURE-INVALID; ZERO C01 PROMPTS; BATCH PAUSED
**Run:** `c01-prestagec-a1-r1`
**Cell:** A1 active, repetition 1
**Behavior aggregation:** excluded
**Harness reliability denominator:** included

## Result

The exact frozen command materialized the fresh workspace and built the complete runtime manifest. Before spawning Pi or sending prompt 1, the manifest identity gate failed 33/34 checks:

- failed: `pi_version` only;
- expected: `0.82.0` inherited from the completed Phase 0.5 runner;
- observed: `0.82.1`;
- Pi package versions remained `0.81.1` for `pi-ai`, `pi-agent-core`, and `pi-coding-agent`;
- provider, focus, consortium, template, model arguments, runner, contract, addendum, scenario, package, dirty-state, and command identities all passed.

The runner exited 2 with:

`RuntimeError: 33/34; failed=['pi_version']`

## No behavioral observation

- prompts delivered: 0;
- model calls: 0;
- live-boundary file: absent;
- RPC/session/consortium behavioral events: absent;
- D1 eligible observations: 0;
- D2 observations: 0;
- D5 bundle/scoring: not derived;
- fixture unchanged from template.

This is dependency drift discovered by the prospective runtime gate, not a failed c01 behavior result.

## Evidence integrity

- evidence root: `.parcour-runs/c01-prestagec-a1-r1/`;
- retained temp root: `/tmp/parcour-c01-prestagec-a1-r1/`;
- evidence files: 13;
- evidence bytes: 23,728;
- evidence-manifest relative path set: exact;
- every recorded SHA-256 and size: exact;
- implementation repository after adjudication: clean.

The run ID and paths are consumed. They must never be deleted, overwritten, retried, or reclassified as behavior-valid.

## Why execution stopped

Frozen c01 validity says wrong runtime identity stops the batch and an infrastructure-invalid cell is not automatically replaced. Report `50`'s serial boundary also requires A1 adjudication before D1. D1 and all later cells therefore remain blocked.

## Prospective choices

### Recommended: runtime-only v9 amendment

Before any c01 prompt:

1. create a new preregistration amendment that preserves v8 and this failed run;
2. pin Pi CLI `0.82.1` for c01 without editing the frozen Phase 0.5 runner;
3. assign replacement A1 ID `c01-prestagec-a1-r1b` and add both `/tmp` path aliases;
4. keep opaque D5 bundle ID `Z8R4`, which has not been derived or scored;
5. change no prompt, fixture, model, extension, ground truth, D1/D2/D5/D7 rule, margin, validity meaning, scorer, rubric, or schedule position;
6. update runner/contract identities, tests, exact A1 command, and independently review the narrow diff;
7. run identity-only preflight, then execute A1b only.

This is not a hidden retry: v8 A1 remains the published infrastructure-invalid first attempt; v9 explicitly names its replacement.

### Alternative: restore Pi CLI 0.82.0

The user may restore the old CLI identity externally. A new run ID and prospective replacement amendment are still required because `c01-prestagec-a1-r1` is consumed. This adds dependency rollback risk and is not recommended while current package identities remain unchanged.

## Required decision

Authorize the recommended runtime-only v9 amendment, or restore Pi CLI 0.82.0 and authorize a replacement-ID amendment. No automatic replacement is permitted.
