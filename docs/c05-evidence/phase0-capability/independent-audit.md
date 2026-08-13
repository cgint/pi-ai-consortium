# c05 Phase 0 independent audit

**Verdict:** BLOCK — preserve attempt; do not freeze or start live c05 prompts

## Passed evidence

- Published `result.json` is byte-identical to the ignored runtime source; SHA-256 `0b43f6c30a418ec7cec44966717773f2a8022fcba8297add91dce810a8c70418`.
- The RPC protocol contains exactly two `get_state` commands and no user prompt.
- Initial and final nested state prove provider `8081-twins`, model `qwen36-27b-nvidia-nvfp4`, and thinking `off`.
- Node `v22.23.2` and Pi `0.84.1` pass the compatibility policy.
- Effective child environment records `CONSORTIUM_MODEL=8081-twins/qwen36-27b-nvidia-nvfp4` despite ambient Google configuration.
- All three extension files exist and independently recomputed SHA-256 values match the result.
- Settings bytes, path, process exit, and repository path confinement pass.
- `[olla] Discovering models...` is provider-discovery stderr, not substitution; both live state responses establish the actual executor identity.

## Blocking defect

The raw-publication dry-run validated `/Users/cgint/dev-external/pi-ai-consortium/docs/c05-phase0-capability`, but the actual durable publication path is `/Users/cgint/dev-external/pi-ai-consortium/docs/c05-evidence/phase0-capability`. The tested destination therefore does not cover the path used for publication.

The state-reported session file was not materialized for this control-only session. Zero-prompt evidence remains available in the recorded RPC command list, runner source, raw stdout, `messageCount: 1`, and absence of any prompt command; no separate raw session transcript is claimed.

## Disposition

This attempt is preserved as Phase 0 harness-invalid evidence. No c05 freeze, review, smoke cell, or matrix cell may begin from it. Correcting the publication destination and executing a fresh Phase 0 attempt requires explicit user authorization under the goal’s retry/runtime-change rule.
