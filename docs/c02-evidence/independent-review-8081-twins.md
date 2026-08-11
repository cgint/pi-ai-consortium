Warning: (startup session lookup, project settings) Unexpected non-whitespace character after JSON at position 128 (line 9 column 1)
Warning: No models match pattern "olla/qwen36-27b-nvidia-nvfp4"
Warning: (runtime creation, project settings) Unexpected non-whitespace character after JSON at position 128 (line 9 column 1)
Warning: (runtime creation, project settings) Unexpected non-whitespace character after JSON at position 128 (line 9 column 1)
**PASS**

**HEADLINE:** c02 ecd0fc9 amendment passes adversarial review. All five prior-failure corrections verified; c02 schedule/corpus/identity/raw-evidence boundaries intact.

---

## Prior Failure Corrections — Verified

### (1) Preflight derives guard state with no workspace read/materialization

**PASS.** `arm_guard_enabled()` (c02_runner.py:70-74) is a pure function of `spec["arm"]`; it returns `True` iff `arm == "on"`. The prefllight path (`runner.preflight()`) calls `_validate_frozen_inputs()` (line 136) which validates commit, runner SHA, corpus SHA, review session SHA, and contract — all against repo-root files and command-line args. Workspace materialization happens only in `_materialize_workspace()` (line 164), which is called by `super().run()`, not by `preflight()`. The guard boolean is derived from the frozen schedule, never from filesystem state.

### (2) Workspace setting validated only after creation, before Pi launch

**PASS.** In `_materialize_workspace()` (lines 164-180): settings.json is written (line 173), then immediately read back and validated (lines 174-176):
```
persisted = json.loads(settings.read_text()).get("consortium", {}).get("stateSupersessionGuard")
self.manifest["workspace_guard_setting"] = persisted
self.manifest["identity_checks"]["workspace_guard_setting"] = persisted is enabled
```
Pi is launched only later via `super().run()` which invokes the parent `C01Runner.run()`. The manifest identity check (`_build_manifest`, line 189) confirms the guard setting matches the arm.

### (3) No-contribution injection telemetry preserves governor reason

**PASS.** In `index.ts` lines 198-204, the NO_CONTRIBUTION path logs:
```ts
logger?.log({
  type: "injection_skipped",
  reason: "NO_CONTRIBUTION",
  governor_reason: result.governorReason,
  probe_count: result.probes.length,
  extractedContext: result.extractedContext,
});
```
The `governor_reason` field carries `result.governorReason` through. The runner's `guard_fired()` (c02_runner.py:78-83) checks for `governor_reason == "Explicit durable-state supersession guard"` on both `injection_complete` and `injection_skipped` events. Test confirms: `test_c02_runner.py:36-42` verifies `guard_fired` matches on `injection_skipped` with the correct `governor_reason`.

### (4) Runner scores this outcome as guard-fired

**PASS.** `guard_fired()` (c02_runner.py:78-83) scans for any event where `type` is `injection_complete` or `injection_skipped` AND `governor_reason == "Explicit durable-state supersession guard"`. The assertion `C02-guard` (line 228) compares `fired == expected_guard` where `expected_guard = arm == "on" and fixture.kind == "positive"`. This correctly scores:
- ON + positive → expects guard fired = true
- ON + control → expects guard fired = false
- OFF + positive → expects guard fired = false
- OFF + control → expects guard fired = false

### (5) Contract rehash includes all changed behavior files

**PASS.** `c02-contract-files.json` lists 11 files covering all behavior surfaces:
- `index.ts` — entrypoint with no-contribution logging path
- `src/types.ts` — types including `DeliberationResult.governorReason`
- `src/config.ts` — `stateSupersessionGuard` default
- `src/governor.ts` — `hasExplicitDurableStateSupersession()` and `shouldDeliberate()`
- `src/core.ts` — dual-governor evaluation (pre-extraction and post-extraction)
- `test/governor.test.ts` — governor unit tests
- `test/core.test.ts` — core integration tests including c02 guard test
- `c02_runner.py` — runner itself
- `test_c02_runner.py` — runner tests
- `c02-supersession-corpus.json` — test corpus
- `docs/c02-fresh-supersession-preregistration.md` — preregistration

All files touched by the c02 amendment are included. The contract verifier (c02_runner.py:97-116) checks SHA-256 of each listed file against the on-disk version.

---

## c02 Boundary Checks

### 48-cell schedule
**PASS.** `RUN_SPECS` (c02_runner.py:61-65): 3 repetitions × 8 fixtures × 2 arms = 48. Verified by `test_c02_runner.py:17`: `len(c02.RUN_SPECS) == 48`. Order is repetition-first, then fixture order, then off/on pair — confirmed by test line 18 showing first 6 IDs.

### Corpus integrity
**PASS.** 8 fixtures (4 positive, 4 control) with unique IDs, relative targets, 3 prompts each. Loader validates schema version, fixture count, kind distribution, and target validity (c02_runner.py:38-56). Positive fixtures carry `current_markers` and `historical_markers`; controls do not.

### Identity constraints
**PASS.** Pi `0.84.1`, Node `v22.23.*`, model `olla/qwen36-27b-nvidia-nvfp4`, thinking `off`. Enforced in `_validate_frozen_inputs()` (lines 153-157) and `_build_manifest()` (line 198 via `exact_model` check using `p.MODEL_PROVIDER`, `p.MODEL_ID`, `p.THINKING_LEVEL`).

### Raw evidence boundaries
**PASS.** `_harvest()` (lines 236-261) copies fixture-before, fixture-after, live-boundary.json, rpc-events.jsonl, raw-incoming.jsonl, outgoing-commands.jsonl, combined-directional.jsonl, rpc-stderr.log, sessions, consortium logs, and final state/entries/stats/text. Evidence manifest with SHA-256 per file generated at end.

### Pre-prompt gates
**PASS.** Preregistration (docs/c02-fresh-supersession-preregistration.md) specifies 5 gates: committed source, passing tests, independent RLM review at correct identity, preflight-only passes, raw evidence destinations tracked. Gate 3 requires the review session to "pin provider/model/thinking and predate preflight" — enforced by `review_session_sha256` check in `_validate_frozen_inputs()` (lines 149-150).

---

## No Contradictions Found

- `hasExplicitDurableStateSupersession()` (governor.ts:13-17) requires both a replacement verb AND a durable artifact pattern — prevents false positives on formatting/comment additions (control fixtures).
- Dual governor evaluation in `core.ts` (lines 78-89 pre-extraction, lines 121-132 post-extraction) ensures the guard fires even when `deliberationNeeded: false` from extraction, because `stateSupersessionGuard` check (governor.ts:64-69) is evaluated before the extraction-based decision.
- `index.ts` no-contribution path (lines 192-210) resets `turnState.deliberation = null` and increments `turnsSinceLastAudit` only on governor-skip (line 172), not on NO_CONTRIBUTION — preserving correct turn counting semantics.

**NOT FOUND:** No issues requiring correction. The amendment is coherent, internally consistent, and correctly implements the four prior-failure fixes plus maintains all c02 experimental boundaries.
