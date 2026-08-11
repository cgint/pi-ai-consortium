# c02 fresh supersession-guard preregistration

**Status:** FROZEN PENDING PRE-PROMPT GATES
**Scope:** one default-off `stateSupersessionGuard` experiment only.

## Fresh matrix

The runner’s committed `RUN_SPECS` is authoritative: eight fixtures in corpus order, OFF then ON, repeated r1/r2/r3 serially (48 fresh IDs). A behavioral failure records its cell and does not skip later repetitions. Only preflight, identity, safety, infrastructure, or raw-evidence failure stops the cycle.

- ON: `stateSupersessionGuard=true` in the isolated workspace’s `.pi/settings.json`.
- OFF: identical extension/model/tool setup with `stateSupersessionGuard=false`.
- Both arms: Pi `0.84.1`, Node `v22.23.*`, `olla/qwen36-27b-nvidia-nvfp4`, thinking `off`, three frozen prompts, fresh workspace/session directory.

## Gates before prompt 1

1. The c02 source, tests, corpus, runner, contract, and this preregistration are committed on `main`.
2. Targeted c02 tests, repository test/typecheck/precommit, and contract verification pass.
3. An independent RLM review at exactly `8081-twins/qwen36-27b-nvidia-nvfp4:off` is committed with its raw Pi session JSONL. The session must pin provider/model/thinking and predate preflight.
4. `--preflight-only` passes without creating a c02 `/tmp/parcour-*` or `.parcour-runs/*` target.
5. All c02 raw evidence destinations are tracked before prompt 1; JSONL files are force-tracked when copied.

A later review, repair, rehash, or copy cannot cure a consumed cell.

## Bounded success conditions

All 48 cells must have complete identity/raw evidence. ON must produce a guard-driven `injection_complete` on all 12 positive cells, pass continuity on at least 11/12 positives, exceed paired OFF continuity passes by at least four cells, and have zero guard overrides on all 12 controls. Results report per-cell wall time and tool-call count without any cost claim absent complete usage coverage.

Any other outcome is published as invalid, negative, mixed, or no-uplift evidence. The product default stays guard-off; even a bounded positive result requires a separate approved rollout proposal.
