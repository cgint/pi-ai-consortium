# c02 final outcome — identity-invalid/no uplift

**Status:** CLOSED — no bounded uplift claim and no default-on change

The first frozen cell, `c02-off-r1-yaml-markdown`, consumed three prompts but is identity-invalid: its consortium trace used `google/gemini-3.5-flash` from `CONSORTIUM_MODEL`, not the required `olla/qwen36-27b-nvidia-nvfp4`. The Pi process exit (`0`) and descriptive continuity result do not cure this identity breach.

## Coverage

| Requirement | Coverage | Result |
| --- | --- | --- |
| Preflight | Attempt 1 invalid before materialization; amended attempt 2 passed with zero prompts/materialization | Valid prospective gate before prompt 1 |
| Matrix | `c02-off-r1-yaml-markdown` only; 47/48 cells unconsumed | Stopped on identity-invalid trace |
| Guard/continuity comparison | No valid ON/OFF pair | Not established |
| Controls | 0/12 ON controls | No interruption finding |
| Bounded uplift | All 48 valid cells and frozen gates required | **Not established** |

The full first-cell raw bundle is tracked at `docs/c02-raw/c02-off-r1-yaml-markdown/`; the invalidity record is `docs/c02-evidence/c02-off-r1-yaml-markdown-identity-invalid.md`. The raw-publication ledger marks all later IDs unconsumed.

No later c02 cell, retry, model substitution, source correction, or rollout is authorized by this result. c01 remains separate historical no-uplift evidence.
