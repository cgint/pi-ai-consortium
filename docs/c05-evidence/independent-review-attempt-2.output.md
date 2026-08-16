Now I have all the data needed. Let me compile my comprehensive review.

---

HEADLINE: PASS

CONTRADICTS: None

NOT FOUND:
- **Synthetic-message exclusion**: The preregistration (`docs/c05-supersession-preregistration.md`) and runner (`c05_runner.py`) make no explicit mention of excluding synthetic messages from the guard evaluation pipeline. However, the guard trigger mechanism is tied to `governor_input` telemetry from `workspace_settings` (`c05_runner.py:329-335`) and the `guard_fired` detector counts only `injection_complete`/`injection_skipped` events with the exact `GUARD_REASON` in the second human turn (`c05_runner.py:337-345`). Synthetic messages would not produce these events, so the exclusion is implicit via the telemetry-based detection rather than explicitly stated. This is acceptable given the guard's design is reactive to real workspace settings, not injected synthetic content.

BLOCKER: None

---

**Detailed adversarial findings (non-blocking gaps):**

### 1. Exact Identities — PASS
- `c05_runner.py:34-36`: `PI_VERSION="0.84.1"`, `NODE_VERSION="v22.23.2"`, model/provider/thinking inherited from `c05_phase0.py` (`8081-twins/qwen36-27b-nvidia-nvfp4/off`). These match Phase 0-B `result.json` observed values at `version_check.observed` and `identity.state_initial.observed`. Contract SHA-256 pins all 30 files including extensions. **Verified.**

### 2. Phase 0 Binding — PASS
- `c05_runner.py:33`: `PHASE0_SHA256` hardcoded to `f9a90f1a...`. `validate_phase0()` (`c05_runner.py:97-108`) verifies SHA, nested identity checks, version checks, and `pass=True`. The `validate_runtime_gate()` (`c05_runner.py:72-95`) re-validates extension hashes, command identity, and child environment against the Phase 0 plan at preflight time. **Verified.**

### 3. Authorized Scorer/Corpus Delta — PASS
- `verify_c05_freeze.py:91-101`: Normalizes c05 corpus by stripping `separator_equivalent_policy_identities` from `requirement-replacement`, then asserts byte-equivalence to c04. Only the `separator_equivalent_policy_identities` metadata key is added. `c05_scorer.py:35-48`: `_requirement_replacement_passes()` uses `release(?:[\s-]+)notes` regex — the sole authorized change. Other positive predicates use literal markers unchanged from c04. **Verified.**

### 4. Default-Off Guard — PASS
- Preregistration states "The guard remains default-off" (`docs/c05-supersession-preregistration.md`, last paragraph). `c05_phase0.py:67-68`: `settings_spec()` sets `stateSupersessionGuard: enabled` where `enabled` is the arm boolean. The runner sets this per-cell based on arm, not globally. No code enables the guard by default. **Verified.**

### 5. Structured-User Causal Fix — PASS
- The scorer correction is narrowly scoped to the `requirement-replacement` fixture's separator recognition (`c05_scorer.py:35-48`). The preregistration describes the c04 defect: scorer matched only `release-notes` literally but corpus prompts ask for `release-notes` while model output may contain `release notes`. The fix relaxes to `release(?:[\s-]+)notes`. **Verified.**

### 6. Control Predicate Derived From Before Text — PASS
- `c05_runner.py:347-362`: `control_regression()` extracts the identity pattern from `before` text using four known patterns, finds exactly one, then checks if it appears active (not negated by historical/superseded/retired/migrated keywords on its own line) and if `RELEASE_STREAM=stable` is present. Test `test_control_regression_derives_identity_from_before_text` (`test_c05_runner.py:287-295`) validates all four control identities. **Verified.**

### 7. Exact 8-Smoke Denominator With 4/4 Positive Fires and 0/4 Controls — PASS
- `c05_runner.py:61`: `SMOKE_SPECS` generates exactly 8 ON smoke specs in fixture order. `smoke_transition()` (`c05_runner.py:364-371`) requires exactly 8 results, 4 positives with `guard_fired=True` and `continuity=True`, 4 controls with `guard_fired=False` and `control_regression=False`, all with valid identity/process/raw and 3 prompts delivered. **Verified.**

### 8. Categorical Matrix Block — PASS
- Preregistration: "Any failed smoke transition categorically blocks every matrix cell" (`docs/c05-supersession-preregistration.md`, Serial schedule section). `c05_controller.py:42-44`: Matrix cells require a committed, hash-pinned smoke decision; `validate_smoke_decision()` returns `False` if `matrix_ready` is not `True`. `test_c05_controller.py:test_smoke_behavioral_exit_continues_smoke_but_categorically_blocks_matrix` confirms the block. **Verified.**

### 9. Exact 48 Order — PASS
- `c05_runner.py:62`: `RUN_SPECS` is `[rep in (1,2,3) for fixture_id in FIXTURE_ORDER for arm in ("off","on")]` = 3 × 8 × 2 = 48. Order within each repetition: yaml-markdown (OFF, ON), policy-retirement (OFF, ON), ..., state-comment-control (OFF, ON). Ledger has 56 entries (8 smoke + 48 matrix) in exact `ALL_SPECS` order. `c05_aggregate.py:53-54`: Validates denominators: 8 smoke, 48 matrix, 12 on-positive, 12 off-positive, 24 controls, 12 on-controls. **Verified.**

### 10. No Retries — PASS
- Preregistration: "There are no retries or substitutions." `C05Runner.run()` (`c05_runner.py:468-525`) executes once; exceptions are captured and published. Controller `execute_once()` (`c05_controller.py:47-53`) runs exactly one subprocess invocation. **Verified.**

### 11. Mandatory Stop Classes — PASS
- `c05_runner.py:373`: `MANDATORY_STOP_ASSERTIONS` = `{C05-process, C05-identity, C05-preflight, C05-trace, C05-protocol, C05-prompts, C05-governor-input, C05-confinement, C05-raw-session, C05-harvest}`. `exit_class()` returns 2 for mandatory-stop failures, 1 for behavioral. Post-harvest raw mismatch forces `exit_class=2` and adds `C05-harvest` (`c05_runner.py:507-515`). **Verified.**

### 12. Atomic Ledger — PASS
- `c05_runner.py:227-235`: `_atomic_json_write()` writes to a temp file with PID-suffixed name, fsyncs, then `os.replace()`. On failure, temp is cleaned up. `consume_ledger_record()` (`c05_runner.py:202-216`) reads current SHA, mutates one record, atomically writes. Test `test_consume_ledger_mutates_one_record_and_atomic_failure_preserves_bytes` verifies preservation on rename failure. **Verified.**

### 13. Raw Evidence Completeness — PASS
- `c05_runner.py:527-541`: `_raw_valid()` checks required files including manifest, result, raw-incoming, outgoing, combined-directional, stderr, final states, fixture before/after, sessions/*.jsonl, consortium/*.jsonl. All files verified against manifest SHA-256 and size. `_harvest()` copies all evidence directories. **Verified.**

### 14. Contract Integrity — PASS
- `c05-contract-files.json`: 30 files, schema `c05-contract-files-v1`, excludes self, ledger, raw, and review paths. `verify_c05_freeze.py:28-56`: Verifies each entry's SHA-256 against current and frozen bytes, rejects duplicates/absolutes/traversal. Required files include runner, scorer, corpus, controller, aggregate, preregistration, Phase 0 result/audit. **Verified.**

### 15. One-Cell Controller — PASS
- `c05_controller.py:29-47`: `next_plan()` returns exactly one runner argv for the first unconsumed cell. Validates contiguity and ordering. Default read-only (no `--execute-next`). Preregistration: "The controller has one-cell authority: it plans or executes exactly one next cell, remains read-only by default." **Verified.**

### 16. Final Uplift/Control Thresholds — PASS
- `c05_aggregate.py:62-66`: Mechanism gate: `on_fires == 12 and off_fires == 0 and control_fires == 0`. Uplift: `mandatory_behavioral_gates and smoke_transition and mechanism and on_count >= 11 and on_count - off_count >= 3 and regressions == 0`. Preregistration matches: "ON continuity at least 11/12 and at least 3 cells above paired OFF, and zero control regressions." **Verified.**

### 17. Ledger/Raw Pre-Absence — PASS
- `raw-publication-ledger.json`: All 56 records `status: "unconsumed"`, matching `ALL_SPECS` order. Each `docs/c05-raw/<id>/` contains only empty `.gitkeep`. No `.parcour-runs/c05-*` runtime targets exist. **Verified.**

### 18. Scorer Test Against c04 Outputs — PASS
- `test_c05_scorer.py:23-28`: All six c04 `requirement-replacement` outputs (3 reps × 2 arms) pass the new scorer. This confirms the separator fix correctly accepts the historical c04 outputs that contained `release notes` (space-separated). **Verified.**

### 19. Review Parser Structure — PASS
- `c05_runner.py:127-156`: `validate_review()` parses the raw session JSONL, validates timing (between freeze and preflight), path confinement, SHA-256 of raw session, model/thinking consistency, and structured PASS verdict in the final assistant message. Rejects `HEADLINE: FAIL` followed by `HEADLINE: PASS` since it checks the last assistant message. **Verified.**

### 20. Telemetry Verification — PASS
- `c05_runner.py:329-345`: `governor_input_valid()` requires `state_supersession_guard` boolean matching arm, `state_supersession_guard_source == "workspace_settings"`, and `current_human_turn_length == len(prompt)` on the second turn. `guard_fired()` counts only `injection_complete`/`injection_skipped` with exact `GUARD_REASON` in the second turn window. **Verified.**

### Minor Observations (Non-Blocking):

1. **`c05_runner.py:62` RUN_SPECS order**: The preregistration says "repetition 1, 2, then 3; within each: yaml-markdown, policy-retirement, requirement-replacement, state-format-migration, state-formatting-control, policy-clarification-control, requirement-addition-control, state-comment-control; each fixture is OFF then ON." The list comprehension `for rep in (1, 2, 3) for fixture_id in FIXTURE_ORDER for arm in ("off", "on")` produces exactly this order. **Consistent.**

2. **`c05_scorer.py:12` HISTORICAL_WORDS**: Includes `"replac"` which could match words like "replacement" in non-historical contexts. However, the scorer applies this only within ±100 characters of the matched identity marker, and the c04/c05 corpus fixtures don't contain such ambiguity. Low risk given the controlled corpus.

3. **`c05_runner.py:422` C05-control assertion**: Maps to `not regression` where regression is only computed for control fixtures. For positive fixtures, `regression` is `False` so `C05-control` always passes for positives. This is correct behavior — the control regression check is only meaningful for controls.

4. **Contract includes `phase05_runner.py`** (base class) but the c05 runner overrides most methods. The base class provides `validate_confinement()` and process management infrastructure. Its inclusion in the contract ensures the inherited validation logic is pinned. **Acceptable.**

5. **`c05_aggregate.py:48`**: `mandatory_behavioral_gates` requires zero `failed_assertions` across ALL 56 cells (smoke + matrix). This is stricter than the preregistration's "all valid mandatory/behavioral raw/identity/process evidence" language but is the correct interpretation — any assertion failure in any cell prevents uplift.

**Conclusion**: The c05 freeze commit is structurally sound. All 20 reviewed dimensions pass. No contradictions between preregistration, contract, code, tests, and ledger. The authorized delta (separator regex + metadata) is minimal and well-tested against historical c04 outputs. The package is ready for preflight.
