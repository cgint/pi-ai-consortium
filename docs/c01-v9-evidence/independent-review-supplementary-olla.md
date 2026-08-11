# c01 v9 Twins — Adversarial Final Review

**OUTPUT:** READ-ONLY static analysis, 9 files, 0 modifications
**HEADLINE:** **PASS** — all 6 claims verified; no BLOCKER identified
**CONTRADICTS:** none found
**NOT FOUND:** D5 bundle IDs in runner (by design: execution/scoring separation, original prereg L86)
**LIMITS:** Live preflight (INV-55) already passed; this review covers code/contract only, no runtime execution

---

## (1) Original A1 preserved; A1b replaces only run_id

| Aspect | Verdict | Evidence |
|--------|---------|----------|
| Schedule unchanged | ✅ | `CHECKPOINT_SCHEDULES["pre-stage-c"]` = ["A1","D1","A2","D2","A3","D3"] — runner L53 |
| Arm/repetition unchanged | ✅ | Derived from cell prefix: `arm="active"` for A-cells, `repetition=int(cell[1])` — runner L67-71 |
| Run_id override | ✅ | `RUN_SPECS["pre-stage-c"]["A1"]["run_id"] = "c01-prestagec-a1-r1b"` — runner L87 |
| D5 bundle unchanged | ✅ | Prereg v9 table matches original prereg L73 (`A1→Z8R4`); runner never encodes D5 bundles (execution/scoring separation per original prereg L86) |
| Original A1 aliases preserved | ✅ | Alias map contains both `a1-r1` and `a1-r1b` entries for `/tmp` and `/private/tmp` |

**Verdict: PASS** — A1 schedule/arm/repetition/D5 bundle intact; only `run_id` changed to `a1-r1b`.

---

## (2) Pi exact 0.84.1, Node only v22.23.*, exact runtime recording, Phase05 unchanged

| Check | Verdict | Evidence |
|-------|---------|----------|
| Pi exact version | ✅ | `C01_PI_VERSION = "0.84.1"` — runner L81; enforced at L531 |
| Node v22.23.* only | ✅ | `C01_NODE_VERSION_PATTERN = r"v22\.23\.\d+"` — runner L82; regex-validated at L532 |
| Exact runtime recording | ✅ | Manifest records `runtime_versions: {pi_cli, node_cli}` — runner L551-552 |
| Phase05 unchanged | ✅ | Frozen blob `cfe4ab…` and sha256 `8297ee…` pinned at L44-45; validated at L464-465 |

**Verdict: PASS** — all four constraints enforced at preflight.

---

## (3) All preflight failures occur before any target creation/harvest

| Gate | Position | Evidence |
|------|----------|----------|
| `_validate_frozen_inputs()` | First | runner L719 — validates 6 identity fields + cell mapping + git blobs |
| `_guard_existing_paths()` | Second | runner L720 — raises `FileExistsError` if tmp_root/workspace/evidence_dir exist |
| `_build_manifest()` | Third | runner L721 — builds runtime identity checks |
| `validate_identities()` | Fourth | runner L722-724 — raises `RuntimeError` if any check fails |
| `_materialize_workspace()` | Fifth (after all above) | runner L737 — first path creation (`mkdir`) |

**Order:** frozen inputs → path guard → manifest → identity → THEN materialize → spawn → prompt → harvest.

**Verdict: PASS** — confirmed by code flow AND tests:
- `test_well_formed_identity_mismatch_fails_before_any_target_path` — test L145-150
- `test_malformed_identity_fails_before_any_target_path` — test L171-178
- `test_runtime_preflight_failure_creates_no_target_paths` — test L159-169

---

## (4) `--preflight-only` cannot materialize, harvest, spawn Pi, or prompt

| Constraint | Evidence |
|------------|----------|
| Routes to `preflight()` not `run()` | runner L774: `runner.preflight() if args.preflight_only else runner.run()` |
| `preflight()` calls only `_preflight()` | runner L726-731 — no materialize, spawn, RPC loop, or harvest |
| Returns `prompts_delivered: 0` | runner L729 |
| Test confirms | `test_cli_preflight_only_never_calls_live_run` — test L72-82: mocks verify `preflight.assert_called_once()`, `run.assert_not_called()` |

**Verdict: PASS** — `--preflight-only` is strictly identity validation only.

---

## (5) Aliases/tests are hash-pinned; tests cover valid/invalid no-target preflight + CLI routing

| Requirement | Verdict | Evidence |
|-------------|---------|----------|
| Alias map hash-pinned | ✅ | `c01-contract-files.json` pins `alias-maps/c01-revision-continuity.json` sha256 `0e58f0…` |
| Runner hash-pinned | ✅ | `c01-contract-files.json` pins `test_c01_runner.py` sha256 `11feb9…` |
| Valid no-target preflight | ✅ | `test_preflight_only_passes_without_target_paths` — test L152-163: asserts `pass=True`, `prompts_delivered=0`, no paths created |
| Invalid no-target preflight | ✅ | `test_well_formed_identity_mismatch_fails_before_any_target_path` — test L145-150: asserts exception, no paths |
| CLI routing | ✅ | `test_cli_preflight_only_never_calls_live_run` — test L72-82 |
| Additional coverage | ✅ | 13 test methods total covering schedules, arm/order, sequencer, D1/D2 capture, fixtures, path diff, cell-not-in-schedule |

**Verdict: PASS**

---

## (6) BLOCKER to live A1b?

**None identified.** Specifically:

- D5 bundles absent from runner is **by design** (original prereg L86: "The runner executes and captures. It never calls the D5 evaluator"). D5 scorer (`c01_d5_scorer.py`) is separately hash-pinned in the contract manifest.
- INV-55 (identity preflight) already passed with zero prompts, no target paths.
- INV-56 status: "PENDING final independent review" — this review fulfills that prerequisite.
- All 23 assertions (C01–C23) are defined and mechanically checkable.
- No contradictions between v9 prereg and runner implementation.

**Verdict: NO BLOCKER**
