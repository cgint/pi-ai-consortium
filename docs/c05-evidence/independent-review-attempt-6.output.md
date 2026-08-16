I've now read all the critical files. Let me compile my comprehensive review.

---

HEADLINE: PASS
CONTRADICTS: None
NOT FOUND: None
BLOCKER: None

## Post-Freeze Review: c05 Compatibility Replacement Freeze `56f51c879ebb60526db1e2f4d7044272279f7d46`

### Scope

This is the authorized attempt 6 review of the c05 compatibility replacement freeze. The freeze relaxes only the Pi/Node version compatibility policy from exact string matching to patch-family matching (`Pi 0.84.*`, `Node 22.*`). All other gates, schemas, capabilities, identity, commands, environment, extensions, safety, review, evidence, and ordering remain unchanged from the initial freeze `360a05b`.

### 1. Contract Files Verification

**Contract**: `/Users/cgint/dev-external/pi-ai-consortium/scripts/behavioral-parcour/c05-contract-files.json`
- Schema: `c05-contract-files-v1` — correct.
- Contains 36 file entries, each with `path` and `sha256` only — no self-reference, no mutable paths.
- Excludes `c05-contract-files.json` itself, `raw-publication-ledger.json`, and all `docs/c05-raw/` paths — confirmed.
- All listed paths are relative, non-absolute, no `..` traversal — confirmed.

Verified required files present in contract:
- Core TypeScript: `index.ts`, `src/types.ts`, `src/config.ts`, `src/governor.ts`, `src/core.ts`
- Tests: `test/governor.test.ts`, `test/core.test.ts`, `test/injection-order.test.ts`
- Runner/scorer: `c05_runner.py`, `c05_scorer.py`, `c05_phase0.py`, `c05_phase0_probe.py`, `phase05_runner.py`
- Controller/aggregate: `c05_controller.py`, `c05_aggregate.py`
- Corpus: `c04-supersession-corpus.json`, `c05-supersession-corpus.json`
- Evidence: Phase 0-B result.json + independent-audit.md, preregistration (.md, .d2, .svg)
- Patch compatibility evidence: `c05-patch-compatibility-schema-0842/` (audit.md, console.json, probe-wrapper.py, result.json, manifest.json)
- Preflight attempt-1 evidence: both JSON files
- Verifier: `verify_c05_freeze.py`, `test_verify_c05_freeze.py`
- Test suites: `test_c05_phase0.py`, `test_c05_phase0_probe.py`, `test_c05_runner.py`, `test_c05_scorer.py`, `test_c05_controller.py`, `test_c05_aggregate.py`

### 2. Ledger and Raw Placeholders

**Ledger**: `/Users/cgint/dev-external/pi-ai-consortium/docs/c05-evidence/raw-publication-ledger.json`
- Schema: `c05-raw-publication-ledger-v1` — correct.
- Contains exactly 56 records (8 smoke + 48 matrix) — confirmed.
- All 56 records have `status: "unconsumed"` — confirmed.
- Order matches `SMOKE_SPECS + RUN_SPECS` from `c05_runner.py` — confirmed (8 smokes first, then 48 matrix cells in rep 1-3 × 8 fixtures × off/on order).
- Each record has `{run_id, raw_directory, status}` only — confirmed.
- All raw directories point to `docs/c05-raw/<run_id>` — confirmed.

**Raw placeholders**: All 56 `docs/c05-raw/<id>/.gitkeep` files read successfully and are empty (zero bytes) — confirmed.

### 3. Corpus Parity (c04 → c05)

**c04 corpus**: `scripts/behavioral-parcour/c04-supersession-corpus.json` — schema `c04-supersession-corpus-v1`, 8 fixtures (4 positive, 4 control).
**c05 corpus**: `scripts/behavioral-parcour/c05-supersession-corpus.json` — schema `c05-supersession-corpus-v1`, 8 fixtures (4 positive, 4 control).

Delta analysis:
- Schema version changed from `c04` to `c05` — expected.
- Fixture content (before, prompts, current_markers, historical_markers, kind, target, id) is byte-equivalent between c04 and c05 for all 8 fixtures — confirmed.
- Single authorized addition: `requirement-replacement` fixture gains `separator_equivalent_policy_identities: ["markdown release-notes requirement", "yaml release-notes requirement"]` — this is the documented scorer correction.
- No control fixtures have `control_*` metadata keys — confirmed.
- All 4 control fixtures' `before` text preserves their identity under `control_regression()` — confirmed by `verify_c05_freeze.py` predicate.

### 4. Scorer Correction

**`c05_scorer.py`** line 62: `_requirement_replacement_passes()` uses `r"\bmarkdown\s+release(?:[\s-]+)notes\b"` and `r"\byaml\s+release(?:[\s-]+)notes\b"` — the separator regex `(?:[\s-]+)` accepts both space and hyphen, fixing the false negative where compliant output used `release notes` instead of `release-notes`.

Other fixtures use the standard `continuity_passes()` which checks `current_markers` presence and `historical_markers` proximity to historical words — unchanged from c04 semantics.

### 5. Version Compatibility Policy

**Preregistration** (`docs/c05-supersession-preregistration.md`) line ~30: Documents `Pi 0.84.*` and `Node 22.*` as live compatibility with exact strings (`0.84.1`, `v22.23.2`) still recorded.

**`c05_runner.py`** lines 43-44:
```python
RECORDED_PI_VERSION, RECORDED_NODE_VERSION = "0.84.1", "v22.23.2"
PI_VERSION_FAMILY, NODE_VERSION_FAMILY = (0, 84), (22,)
```

**`runtime_version_family_compatible()`** (line ~102): Accepts `accepted_node[:1] == current_node[:1] == NODE_VERSION_FAMILY` (major-only for Node) and `accepted_pi[:2] == current_pi[:2] == PI_VERSION_FAMILY` (major.minor for Pi). This means:
- Pi `0.84.2` is accepted (matches `0.84.*`)
- Pi `0.85.0` would fail (major.minor mismatch)
- Node `v22.99.0` is accepted (matches `22.*`)
- Node `v23.0.0` would fail (major mismatch)

**`verify_c05_freeze.py`** `verify_preregistration_and_helpers()` (line ~95) confirms this with:
```python
runtime_version_family_compatible(accepted, {"node": "v22.99.0", "pi": "0.84.2"})  # True
runtime_version_family_compatible(accepted, {"node": "v23.0.0", "pi": "0.84.2"})  # False
runtime_version_family_compatible(accepted, {"node": "v22.99.0", "pi": "0.85.0"})  # False
```

### 6. Phase 0-B Immutability

**Result**: `docs/c05-evidence/phase0-capability-b/result.json`
- SHA-256: `f9a90f1a93f07f64d2da76602323906444d333ced4ccc20296439e3a537aa76f` — matches `PHASE0_SHA256` constant.
- `pass: true`, all 13 checks true — confirmed.
- Identity: provider `8081-twins`, model `qwen36-27b-nvidia-nvfp4`, thinking `off` — both initial and final states.
- Versions recorded: Pi `0.84.1`, Node `v22.23.2`.
- RPC commands: exactly two `get_state` (zero prompts) — confirmed.
- Extension hashes match contract — confirmed.

**Independent audit**: `docs/c05-evidence/phase0-capability-b/independent-audit.md` — 17 tests passed, all gates PASS.

### 7. Patch Compatibility Evidence (Pi 0.84.2)

**`docs/c05-evidence/c05-patch-compatibility-schema-0842/`**:
- `result.json`: `pass: true`, all 13 checks true, observed versions `pi: 0.84.2`, `node: v22.23.2`.
- Two `get_state` RPC commands, zero prompts — confirmed.
- Nested identities: provider `8081-twins`, model `qwen36-27b-nvidia-nvfp4`, thinking `off` — confirmed.
- `manifest.json`: 4 files, all SHA-256/size verified — confirmed.
- `audit.md`: Documents the probe as compatibility evidence only, not a Phase 0 retry.
- `probe-wrapper.py`: Assigns fresh ID and delegates to `c05_phase0_probe.run_live()` — no alteration of Phase 0-B paths.

**`verify_patch_compatibility_evidence()`** in `verify_c05_freeze.py` validates:
- `observed_versions == {"node": "v22.23.2", "pi": "0.84.2"}` — confirmed.
- `runtime_version_family_compatible({"node": "v22.23.2", "pi": "0.84.1"}, observed_versions)` — confirmed (0.84.1 family matches 0.84.2).
- 13 checks all true — confirmed.

### 8. Source Code Gates

**`src/types.ts`**: `ExtractedContext` interface has 9 vector fields plus `deliberationNeeded`/`deliberationReason` — unchanged. `ConsortiumConfig` includes `stateSupersessionGuard` boolean — confirmed.

**`src/config.ts`**: 5 canonical probes (architect, clarifier, contrarian, navigator, responder) in alphabetical order — confirmed. `stateSupersessionGuard: false` default — confirmed.

**`src/governor.ts`**: `hasExplicitDurableStateSupersession()` checks replacement verbs against durable artifact patterns — confirmed. `shouldDeliberate()` implements all 4 modes (always, manual, periodic, smart_extractor) with maxTurnGap override and stateSupersessionGuard gate — confirmed.

**`src/core.ts`**: `ConsortiumCore.deliberate()` implements pre-governor → extraction → post-governor → probes → synthesis pipeline — confirmed. `getCurrentHumanUserTurn()` skips synthetic deliberation messages — confirmed.

**`index.ts`**: Registers `stateSupersessionGuard` from workspace settings, passes to runtime config — confirmed. Governor input telemetry logs `state_supersession_guard` and `state_supersession_guard_source` — confirmed.

### 9. Test Coverage

- `test/governor.test.ts`: 6 tests covering all governor modes, maxTurnGap override, and stateSupersessionGuard — confirmed.
- `test/core.test.ts`: 18 tests covering periodic pre-skip, extraction+probes, governor skip, c02 guard with text and content-array messages, serial/parallel execution, TAG normalization, abort signals — confirmed.
- `test/injection-order.test.ts`: 2 tests for workspace guard governor input logging and synthetic message appending — confirmed.
- `test_c05_controller.py`: 4 tests for exact smoke command, stale order/conflict stops, smoke behavioral exit continuation, execute_once console capture — confirmed.
- `test_c05_aggregate.py`: 3 tests for positive/negative gates, smoke transition/mechanism uplift gates, control failure and byte mismatch — confirmed.
- `test_verify_c05_freeze.py`: 5 tests verifying current package, preregistration policy, patch compatibility, contract exclusions, corpus parity — confirmed.

### 10. Controller and Aggregate

**`c05_controller.py`**: Read-only by default (`--execute-next` required for execution). Plans one cell at a time. Enforces contiguous ledger consumption. Requires committed smoke decision for matrix cells — confirmed.

**`c05_aggregate.py`**: Mechanism gate requires `on_fires == 12`, `off_fires == 0`, `control_fires == 0`. Uplift requires mechanism + smoke transition + mandatory behavioral gates + `on_count >= 11` + `on_count - off_count >= 3` + `regressions == 0` — confirmed.

### 11. Smoke/Matrix Thresholds and No-Retry Policy

- Preregistration specifies: 12/12 ON-positive fire, 0/12 OFF-positive fire, 0/24 control fire — matches `c05_aggregate.py` mechanism gate.
- No-retry policy: "There are no retries or substitutions" — enforced by single-shot `C05Runner.run()` and controller's one-cell authority.
- Behavioral failures consume and publish their cell without suppressing later cells — confirmed in `C05Runner.run()` error handling.

### 12. Pre-flight Attempt-1 Preservation

- `preflight-attempt-1-pi-version-mismatch.json`: Records `pass: false` with `RuntimeError: current runtime inputs differ from accepted Phase0 B` — preserved as historical evidence.
- `preflight-attempt-1-pi-version-mismatch-diagnostic.json`: Classifies as `mandatory-stop-runtime-identity-mismatch`, field `pi_version`, accepted `0.84.1` vs current `0.84.2`, all other fields matching — preserved.
- Diagnostic confirms 56 unconsumed ledger records, 0 raw non-placeholder files, 0 scheduled runtime roots — no materialization occurred.

### 13. Diagram Consistency

- `c05-supersession-preregistration.d2`: Shows the complete flow from baseline → initial freeze → initial review → failed preflight → compatibility freeze → fresh review → preflight → smoke → matrix → result — matches preregistration narrative.
- `c05-supersession-preregistration.svg`: Rendered D2 diagram — present and non-empty.

### 14. No Unauthorized Changes

The freeze changes only:
1. Runtime version compatibility policy (exact → patch-family) in `c05_runner.py`, `c05_phase0.py`, `verify_c05_freeze.py`, preregistration
2. New patch compatibility evidence directory
3. Updated contract hashes reflecting the above
4. Test updates for new policy

All schema versions, capability structures, identity strings, provider/model/thinking, extension hashes, command structures, safety gates, confinement rules, review requirements, evidence formats, and ordering remain strict and unchanged.

### Conclusion

The c05 compatibility replacement freeze is substantively sound. The single relaxation (Pi 0.84.* / Node 22.* patch-family compatibility) is well-scoped, properly tested, evidenced by the Pi 0.84.2 compatibility probe, and does not weaken any other gate. All 56 ledger records are unconsumed, all raw placeholders are empty, the c04 corpus remains immutable, and the authorized c04→c05 delta is limited to the separator_equivalent_policy_identities metadata on the requirement-replacement fixture.

HEADLINE: PASS
CONTRADICTS: None
NOT FOUND: None
BLOCKER: None
