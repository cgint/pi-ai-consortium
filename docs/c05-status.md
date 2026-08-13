# c05 status

**Status:** Phase 0 implementation ready; live zero-prompt capability probe pending
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
- All new transient/cache writes are confined beneath the repository’s ignored `.parcour-runs/` path.

## Compatibility policy

- Node and Pi versions are recorded as provenance; compatibility accepts Node 22+ and the package-supported Pi range `>=0.74.0,<1.0.0` before capability checks.
- Provider/model/thinking identity is never inferred from version or command construction: live nested `get_state` must prove it.
- Child `CONSORTIUM_MODEL` is always overwritten with `8081-twins/qwen36-27b-nvidia-nvfp4`, including when ambient state points to Google.
- Extension existence and SHA-256, exact settings location/payload, reviewer command shape, repository path confinement, and zero-prompt RPC methods are checked explicitly.

## Measurement issue requiring resolution before freeze

The c04 `requirement-replacement` scorer requires literal hyphenated marker strings, while all six OFF/ON outputs preserve the requested semantic current and superseded policies using equivalent “release notes” wording. This is a verified scorer defect, not a behavioral failure. Correcting it pre-freeze would reclassify c04 semantically to 11/12 in both arms; c04 itself will not be changed.

No c05 predicate, fixture, threshold, or corpus has been frozen or changed yet. The live Phase 0 probe and its exact observed evidence come next; then this measurement decision must be resolved before c05 freeze.
