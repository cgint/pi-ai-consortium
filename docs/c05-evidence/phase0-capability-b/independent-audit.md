# c05 Phase 0 capability B — independent audit

**Verdict: PASS**

**Audit scope:** `c05-phase0-capability-b-executable-audit-01`

**Method:** No Pi execution or prompts. Only the three prescribed deterministic c05 modules were run, with repo-local temporary writes.

## Test execution

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.parcour-runs/c05-test-tmp" \
  python3 -m unittest \
  scripts/behavioral-parcour/test_c05_phase0.py \
  scripts/behavioral-parcour/test_c05_phase0_probe.py \
  scripts/behavioral-parcour/test_c05_scorer.py
```

Result: **17 tests passed** (`Ran 17 tests in 0.004s`, `OK`).

## Mandatory-gate verification

| Gate | Independent observation | Result |
| --- | --- | --- |
| Exact identity | Initial and final `get_state`: provider `8081-twins`, model `qwen36-27b-nvidia-nvfp4`, thinking `off`; both responses successful | PASS |
| Zero prompts / exact RPC lifecycle | Plan declares only `state_initial` and `state_final`, both `get_state`; both state records report `messageCount: 1` | PASS |
| Validated and actual destination | Exact authorized root: `docs/c05-evidence`; only destination: `docs/c05-evidence/phase0-capability-b`; recorded dry run passed | PASS |
| Byte identity | `result.json`: both copies SHA-256 `f9a90f1a93f07f64d2da76602323906444d333ced4ccc20296439e3a537aa76f`; settings: both copies SHA-256 `fe5e91ab6b8c88e9225b6c24e0f91dd5ca3550a088db74748b97281b3d9db07f` | PASS |
| Exact settings | Both copies contain enabled consortium, `governorMode: smart_extractor`, and `stateSupersessionGuard: true` | PASS |
| Versions | Recorded commands exited 0: Node `v22.23.2`, Pi `0.84.1`; compatibility checks passed | PASS |
| Extension hashes | Live SHA-256 values equal recorded values: focus guard `8a4383eef13551749c3065199b9b734714478a00a508157177a3c4f105a9f0b1`; olla autodetect `4abcf40187c3d40bb8c6f68f4ebb2b226aa9aa73c0213f89a2f2da0576101039`; consortium `7b0c7a306987e12cbd2e369f56a9dfb4deb91f3f6720eecc84e9ba5d5a024fdb` | PASS |
| Process exit | Recorded `process_returncode: 0`; `failure: null`; aggregate result `pass: true` | PASS |
| c04 / attempt-1 immutability | No current working-tree changes under the checked c04 evidence/audit or attempt-1 paths. The recorded correction is classification-only and explicitly preserves the underlying attempt evidence. | PASS |
| Test-only lifecycle correction | The sole pre-existing source diff is in `test_c05_phase0_probe.py`; it makes the destination-exists conflict/pass expectation explicit and changes no production code or evidence. | PASS |

## Working-tree check

Before and after tests, the same pre-existing entries remained: modified `scripts/behavioral-parcour/test_c05_phase0_probe.py`; untracked c05 evidence and handoff documents. The test run created only the authorized ignored repo-local temporary directory. This audit adds only this authorized report.

## Limitation

This verifier did not execute Pi, prompt a model, retry the probe, or write outside the authorized audit/temp locations. The execution findings are independently checked from the retained result, settings, byte comparisons, live extension hashes, and deterministic test suite.
