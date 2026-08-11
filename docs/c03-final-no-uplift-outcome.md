# c03 final outcome — harness-invalid/no uplift

**Status:** CLOSED — no bounded uplift claim and no default-on change

c03 correctly pinned both executor and consortium deliberation to `8081-twins/qwen36-27b-nvidia-nvfp4:off`. However, the first frozen cell is harness-invalid because its executor validator read the wrong Pi `get_state` schema. The mandatory-stop exit code ended the matrix after one consumed cell.

## Evidence and coverage

| Requirement | Coverage | Result |
| --- | --- | --- |
| Prospective freeze/review/preflight | Freeze `486882a`; exact session-backed review PASS; preflight passed with zero prompts/targets | Passed before prompt 1 |
| Effective identities | Child env, executor session, final state, and six consortium starts | Correct `8081-twins/qwen36-27b-nvidia-nvfp4:off` |
| Matrix | `c03-off-r1-yaml-markdown` only; 47/48 IDs unconsumed | Stopped on harness-invalid executor assertion |
| OFF/ON comparison | 0 valid pairs | Not established |
| Positive/control gates | No complete denominators | Not established |
| Bounded uplift | Requires all 48 valid cells and all frozen gates | **Not established** |

## Invalidity

Pi `0.84.1` returns executor identity at `get_state.data.model.provider` and `.id`. The frozen runner checked `get_state.data.provider` and `.modelId`, yielding `None` for both and stop exit code `2`. Raw state/session/consortium evidence proves the actual identity was correct, but the protocol does not permit repairing or reclassifying the consumed cell.

The complete raw bundle is tracked at `docs/c03-raw/c03-off-r1-yaml-markdown/`; detailed classification is at `docs/c03-evidence/c03-off-r1-yaml-markdown-harness-invalid.md`. The c03 ledger leaves every later ID unconsumed. c01 and c02 remain separate historical no-uplift evidence.
