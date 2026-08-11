Warning: No models match pattern "olla/qwen36-27b-nvidia-nvfp4"
**HEADLINE: PASS — no blocker found**

**CONTRADICTS (verified, no contradiction found):**

1. **Default-off config reaches core:** `stateSupersessionGuard` defaults to `false` in `src/config.ts:107`. The `index.ts` entrypoint loads it from persisted settings (`index.ts:105`) or keeps the JS default (`index.ts:34`), passes it into `runtimeConfig` (`index.ts:161`), which flows into `ConsortiumConfig` (`index.ts:399-418`), then into `ConsortiumCore` (`index.ts:489`). The governor reads `config.stateSupersessionGuard` at `src/governor.ts:64`. Chain is intact.

2. **Predicate requires explicit replacement verb + durable artifact and respects mode precedence:** `hasExplicitDurableStateSupersession` (`src/governor.ts:13-17`) requires both `hasReplacementVerb` (regex: replace/supersede/retire/migrate variants) AND `hasDurableArtifact` (PROJECT_STATE.md or *.yaml/*.yml). The guard check at `src/governor.ts:64` is gated behind `config.stateSupersessionGuard === true`, and sits **below** the `maxTurnGap` check (`src/governor.ts:57-62`) but **above** the extractor signal (`src/governor.ts:71-84`), meaning `always`/`periodic`/`maxTurnGap` take precedence. Test confirms: `test/governor.test.ts:107-108` verifies the guard is bypassed when `stateSupersessionGuard: false`.

3. **Core uses current user turn:** `src/core.ts:113-118` extracts the latest user message via reverse iteration over the message array, binding `currentUserTurn`, which is passed to `shouldDeliberate` at `src/core.ts:121`. Correct.

4. **Injection telemetry records trigger reason:** When governor skips, `index.ts:176-181` logs `{ type: "injection_skipped", reason: result.governorReason || "SKIPPED_BY_GOVERNOR", ... }`. When injection completes, `index.ts:225-234` logs `{ type: "injection_complete", ..., governor_reason: result.governorReason, ... }`. The `governorReason` originates from `src/core.ts:85` and `src/core.ts:129`, carrying the governor's `reason` string. Verified.

5. **Corpus 4/4 and 3 prompts:** `scripts/behavioral-parcour/c02-supersession-corpus.json` contains exactly 8 fixtures: 4 positive (`yaml-markdown`, `policy-retirement`, `requirement-replacement`, `state-format-migration`) and 4 control (`state-formatting-control`, `policy-clarification-control`, `requirement-addition-control`, `state-comment-control`). Each has exactly 3 prompts. Runner validates this at `c02_runner.py:43-55`.

6. **Schedule 48 ordered OFF/ON repeats:** `c02_runner.py:59-62` generates `RUN_SPECS` as a triple nested loop: 3 repetitions × 8 fixtures × 2 arms = 48. Order is OFF then ON per fixture per repetition. Test confirms at `test_c02_runner.py:17-23`: 48 specs, correct first six IDs, repetitions {1,2,3}, arms {"off","on"}.

7. **Behavioral failures do not suppress repeats:** Preregistration states (`docs/c02-fresh-supersession-preregistration.md:8`): "A behavioral failure records its cell and does not skip later repetitions. Only preflight, identity, safety, infrastructure, or raw-evidence failure stops the cycle." The runner itself does not implement inter-run gating (each run is independent via `--run-id`); the preregistration rule governs orchestration. Consistent.

8. **Preflight checks sources/corpus/contract/review before materializing:** `c02_runner.py:125-146` `_validate_frozen_inputs` verifies: run spec matches schedule, product commit matches HEAD, runner SHA matches, corpus SHA matches, review session SHA matches, contract verification passes, Pi version is `0.84.1`, Node version matches `v22.23.*`. All before `_materialize_workspace`.

9. **Raw capture/ledger is complete:** `_harvest` method (`c02_runner.py:221-246`) copies: manifest, fixture-before, fixture-after, live-boundary.json, rpc-events.jsonl, raw-incoming.jsonl, outgoing-commands.jsonl, combined-directional.jsonl, rpc-stderr.log, sessions dir, consortium logs, state_final/entries_final/stats_final/text_final JSON, result.json, and evidence-manifest.json. Comprehensive.

10. **Contract covers behavior-defining files:** `c02-contract-files.json` lists 11 files: `index.ts`, `src/types.ts`, `src/config.ts`, `src/governor.ts`, `src/core.ts`, `test/governor.test.ts`, `test/core.test.ts`, `c02_runner.py`, `test_c02_runner.py`, `c02-supersession-corpus.json`, and the preregistration doc. All behavior-defining source, test, corpus, runner, and specification files are covered.

**NOT FOUND (items checked but not explicitly present — assessed as acceptable):**

- No explicit test for the `hasExplicitDurableStateSupersession` function in isolation exists in the supplied test files. However, it is exercised indirectly through `test/governor.test.ts:82-109` (the "forces deliberation only for an enabled explicit durable-state supersession" test) and `test/core.test.ts:129-148` (the core integration test). Not a blocker — the function is tested via the public `shouldDeliberate` API.

**BLOCKER: None.**

All ten checklist items verify against the supplied evidence. The predicate logic is correct (AND of replacement verb + durable artifact), mode precedence is properly ordered (always > periodic/maxTurnGap > supersession guard > extractor signal), telemetry captures governor reasons on both skip and injection paths, the corpus is balanced 4/4 with 3 prompts each, the schedule produces 48 ordered runs, preflight validates all frozen inputs before workspace creation, and the contract pins all behavior-defining files.
