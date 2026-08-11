Warning: No models match pattern "olla/qwen36-27b-nvidia-nvfp4"
HEADLINE: PASS; CONTRADICTS: None; NOT FOUND: None; BLOCKER: None

**Adversarial preflight review — c03 freeze 486882a**

**Identity & executor command:** Runner pins `8081-twins/qwen36-27b-nvidia-nvfp4:off` at every layer — CLI flags (`c03_runner.py:31-34`, `:89-91`), child env override (`:85-86`), and post-run trace assertion (`:445-446`). Ambient `CONSORTIUM_MODEL` is explicitly overridden (`test_c03_runner.py:35-38` confirms Google is clobbered). ✅

**Fresh c03-only isolation:** 48 IDs in ledger (`raw-publication-ledger.json` lines 1-245), all `unconsumed`, all prefixed `c03-`. Schedule is `repetition × fixture × arm` = 3 × 8 × 2 = 48 (`c03_runner.py:65-69`). No c02 artifact referenced as a gate or repetition (`preregistration.md:5`). ✅

**Preflight records/validates before materialization:** `_validate_frozen_inputs()` (`c03_runner.py:267-304`) checks contract SHA, review session SHA, Pi version, Node version, executor provider/model/thinking, extension order, child env — all before `_materialize_workspace()` runs. `_preflight()` calls `_validate_frozen_inputs()` then `verify_publication_ledger()` then `_guard_existing_paths()` then `_build_manifest()` (`:328-332`). Materialization happens only in `run()` after preflight passes (`:490`). ✅

**Initial and per-cell path guards are distinct:** Initial guard checks ALL 96 paths via `run_target_paths(RUN_SPECS)` returning 96 unique paths (`test_c03_runner.py:23-24`); per-cell guard checks only 2 paths for the single spec (`:25`). `_guard_existing_paths(all_targets=True)` in preflight vs `_guard_existing_paths(all_targets=False)` in run (`:308-311`, `:329`). ✅

**Post-run identity gates:** `C03-executor-provider`, `C03-executor-model`, `C03-executor-thinking` check both initial and final `get_state` responses (`:436-438`). `C03-trace-identity` checks every `deliberation_start` event has model `8081-twins/qwen36-27b-nvidia-nvidia-nvfp4` and source `CONSORTIUM_MODEL` (`:445-446`). ✅

**Review identity + verdict + timing:** `verify_review_session()` checks session name starts with `c03-8081-twins`, provider=model=thinking, PASS verdict, no blocker (`:135-152`). Timing: `freeze < review ≤ preflight` (`:126-132`, tested at `test_c03_runner.py:40-43`). ✅

**Ledger validation:** `verify_publication_ledger()` checks schema, 48 run IDs in exact order, raw directories exist and are git-tracked, all `unconsumed` (`:157-176`). ✅

**Contract covers every behavior-defining file:** 15 files in contract (`c03-contract-files.json`): entrypoint, types, config, governor, core, both tests, phase05 runner, c03 runner, c03 tests, corpus, preregistration doc/diagram/svg — all behavior-defining paths covered. ✅

**Behavior vs. identity failure handling:** Identity/assertion IDs (`C03-process`, `C03-executor-*`, `C03-preflight-identities`, `C03-trace-identity`) return exit code 2 (stop); behavioral failures (guard, continuity) return exit code 1 (continue) (`:524-526`). Preregistration confirms: "Behavioral failures continue through all frozen repetitions. Identity, review, preflight, infrastructure, safety, or raw-evidence failure stops the cycle." (`preregistration.md:41-42`). ✅

**Raw harvesting completeness:** `_harvest()` copies manifest, fixture before/after, live-boundary, RPC events, raw incoming/outgoing/directional, stderr, sessions, consortium logs, all four final query responses, result.json, evidence manifest (`:460-484`). ✅

**No stale Olla execution dependency, no retrospective review, serial cells executable after preserved earlier cells:** Runner is self-contained with frozen inputs; no external dependency on prior c02 runs. Serial cell sequencing via `C03Sequencer` delivers prompts in order, waits for `agent_settled` between each (`:208-246`). Preflight-only leaves no temp paths (`preregistration.md:50`). ✅
