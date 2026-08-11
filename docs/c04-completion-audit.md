# c04 completion audit

**Status:** COMPLETE VALID NEGATIVE — all deliverables/evidence exist; bounded uplift gate failed
**As-of:** 2026-08-11

## Requirement-to-evidence checklist

| Explicit requirement | Concrete evidence | Audit result |
| --- | --- | --- |
| Preserve c03 unchanged | `git diff --name-only 5c92f85..HEAD -- docs/c03* scripts/behavioral-parcour/c03*` returned empty | Pass |
| Fresh c04 plan, runner, contract, IDs, corpus, tests, ledger, paths | Freeze `c07bf19`; `docs/c04-supersession-preregistration.md`; `scripts/behavioral-parcour/c04_*`; `docs/c04-evidence/raw-publication-ledger.json`; `docs/c04-raw/c04-*/` | Pass |
| Byte-identical Pi 0.84.1 state fixture with provenance | `c04-fixtures/pi-0.84.1-get-state.json`; `provenance.json`; source/fixture SHA equality; direct `cmp` before freeze | Pass |
| Nested-state validator and negative schema tests | `validate_executor_state()` plus nine passing `test_c04_runner.py` tests; obsolete top-level, missing, malformed, and wrong-thinking cases fail | Pass |
| Exact executor and consortium identity | Every manifest pins command/env; aggregate records 48/48 identity-valid; each executor and trace assertion passed | Pass |
| Ambient Google model overridden | Deterministic c04 test passes; every manifest records effective `CONSORTIUM_MODEL=8081-twins/qwen36-27b-nvidia-nvfp4` | Pass |
| Prospective tests/contract/review/preflight | Full precommit: 445/445 tests, typecheck, zero audit vulnerabilities; exact session-backed review PASS; zero-materialization preflight `f6ea95b` | Pass |
| Review after freeze and before prompt 1 | Freeze `c07bf19`; session timestamp verified by preflight; review evidence committed before preflight and first live cell | Pass |
| Exact 48-cell order and no substitutions | Ledger order matches frozen `RUN_SPECS`; 48/48 consumed; all process return codes 0 and prompt counts 3 | Pass |
| Preserve all raw evidence byte-identically | `raw-publication-verification.txt`: 48 bundles, 1,008 source files, zero failures; all copies tracked; all evidence manifests verify | Pass |
| Mandatory post-run identities | `c04-aggregate-result.json`: 48/48 identity-valid and clean process/prompt cells | Pass |
| Publish per-cell identity/guard/continuity/control/time/tool calls | `c04-aggregate-result.json` contains 48 cell records and 24 pairs | Pass |
| Claim uplift only if all gates pass | Mechanism 0/12; continuity ON 8/12, OFF 8/12, delta 0; controls 0/12; report states no uplift/default change | Pass |
| Leave unrelated `.gitignore` untouched | Final `git status --short` shows only `M .gitignore` plus pending c04 report artifacts before their commit | Pass |

## Verification commands

- `python3 -m unittest scripts/behavioral-parcour/test_c04_runner.py` — 9/9 passed.
- `npm run precommit` — typecheck passed, 445/445 tests passed, 0 audit vulnerabilities.
- Frozen `verify_contract(...)` and `verify_state_fixture()` — passed.
- Ledger audit — 48 records, zero unconsumed.
- Raw publication audit — 1,008/1,008 source files tracked and byte-identical; 48/48 evidence manifests passed.

## Final disposition

c04 is a valid, complete negative experiment—not an invalid run. The infrastructure, schema, review, identity, repetition, and evidence gates all passed. The intervention did not fire on any positive ON cell and produced no continuity delta, so no bounded uplift or rollout is supported. The guard remains default-off.
