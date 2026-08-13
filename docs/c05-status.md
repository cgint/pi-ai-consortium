# c05 status

**Status:** Phase 0 attempt 2 independently passed; c05 freeze artifacts next; no behavioral prompt started
**As-of:** 2026-08-13

## Diagram

![c05 gated path](./c05-status.svg)

## Goal

Diagnose and minimally fix the supersession guard’s inactive causal path, then establish or reject bounded continuity uplift with fresh c05 evidence.

## Verified facts

- c04 remains unchanged and is the immutable valid-negative baseline.
- All eight inspected c04 repetition-one ON sessions encode human input as Pi text-part arrays.
- `src/core.ts` previously selected only string-valued user messages, producing an empty guard input while extraction independently recognized supersession.
- Two regression tests first failed with only extraction executed, then passed after normalizing the latest human user turn and excluding `[CONSORTIUM DELIBERATION]` synthetic messages.
- Runtime telemetry now records effective guard value, its settings provenance, and normalized turn length without logging turn text.
- A production-registration test proves workspace settings yield `state_supersession_guard=true`, source `workspace_settings`, and nonzero structured-turn length.
- Capability-first Phase 0 helpers and zero-user-prompt probe have 13/13 deterministic tests passing.
- Full repository gate passes: typecheck, 448/448 tests, and zero audit vulnerabilities.
- The first live Phase 0 attempt proved exact runtime identity and sent only two `get_state` controls, but independent audit found its publication dry-run tested `docs/c05-phase0-capability` rather than the actual `docs/c05-evidence/phase0-capability` destination.
- That attempt remains preserved as harness-invalid at `docs/c05-evidence/phase0-capability/`.
- Authorized attempt 2 uses fresh ID `c05-phase0-capability-b`; its plan records `docs/c05-evidence/phase0-capability-b`, dry-runs that exact destination, and fails unless returned and planned destinations match.
- The c05-owned eight-fixture corpus preserves all c04 fixture content and ordering; only `requirement-replacement` adds the authorized separator-equivalence scoring metadata.
- The c05 scorer accepts `release notes`/`release-notes` only when Markdown is affirmatively current, YAML is explicitly historical/superseded, and `RELEASE_STREAM=stable`; all six tracked historical outputs pass and adversarial negated-current forms fail.
- Attempt 2 ran once from committed harness `ff1a85e`; exactly two `get_state` controls returned the required nested identity and the exact tested publication destination was used byte-identically.
- Independent executable audit passed all Phase 0 gates and independently ran 17/17 c05 Python tests; full repository checks remain 448/448 tests with zero audit vulnerabilities.
- No c05 freeze, smoke prompt, or matrix prompt has started.
- All new transient/cache writes are confined beneath the repository’s ignored `.parcour-runs/` path.

## Compatibility policy

- Node and Pi versions are recorded as provenance; compatibility accepts Node 22+ and the package-supported Pi range `>=0.74.0,<1.0.0` before capability checks.
- Provider/model/thinking identity is never inferred from version or command construction: live nested `get_state` must prove it.
- Child `CONSORTIUM_MODEL` is always overwritten with `8081-twins/qwen36-27b-nvidia-nvfp4`, including when ambient state points to Google.
- Extension existence and SHA-256, exact settings location/payload, reviewer command shape, repository path confinement, and zero-prompt RPC methods are checked explicitly.

## Measurement issue requiring resolution before freeze

The c04 `requirement-replacement` scorer requires literal hyphenated marker strings, while all six OFF/ON outputs preserve the requested semantic current and superseded policies using equivalent “release notes” wording. This is a verified scorer defect, not a behavioral failure. Correcting it pre-freeze would reclassify c04 semantically to 11/12 in both arms; c04 itself will not be changed.

The c05 corpus/scorer correction remains prospective and tested but not yet frozen. Next: create and verify fresh c05 runner, contract, preregistration, smoke/matrix IDs, and raw-publication ledger; then freeze before prospective review, preflight, or any behavioral prompt.
