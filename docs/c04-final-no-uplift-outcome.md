# c04 final outcome — valid negative/no uplift

**Status:** CLOSED — complete 48-cell matrix; no bounded uplift and no default-on change

c04 successfully corrected the infrastructure and identity failures from earlier protocols: every cell used `8081-twins/qwen36-27b-nvidia-nvfp4:off`, all nested Pi 0.84.1 executor-state assertions passed, and all raw bundles are complete. The proposed supersession guard nevertheless produced **no observed mechanism or continuity uplift**.

## Frozen gate result

| Gate | Frozen threshold | Observed | Result |
| --- | --- | --- | --- |
| Identity/integrity | 48/48 valid cells | 48/48 identities; 48/48 clean processes and three prompts | Pass |
| Mechanism | ON guard reason on 12/12 positive cells | **0/12** | **Fail** |
| Continuity | ON ≥11/12 and at least +4 over OFF | ON **8/12**; OFF **8/12**; delta **0** | **Fail** |
| Interruption control | 0/12 ON control guard fires | **0/12** | Pass |
| Bounded uplift | Every gate passes | Mechanism and continuity failed | **Not established** |

No composite or pooled score is used. The interruption-control pass cannot compensate for absent mechanism or uplift.

## Named positive fixtures

| Fixture | OFF continuity | ON continuity | ON guard fires |
| --- | ---: | ---: | ---: |
| `yaml-markdown` | 3/3 | 3/3 | 0/3 |
| `policy-retirement` | 3/3 | 3/3 | 0/3 |
| `requirement-replacement` | 0/3 | 0/3 | 0/3 |
| `state-format-migration` | 2/3 | 2/3 | 0/3 |

On the state-changing `c04-on-r1-yaml-markdown` turn, raw extraction recognized the YAML-to-Markdown supersession but returned `deliberationNeeded:false`; telemetry recorded `injection_skipped` rather than the exact supersession-guard reason. The same mechanical guard result (false) occurred across all 12 ON-positive cells. This is negative mechanism evidence, not a reason to tune or rerun c04.

## Cost/time boundary

All 48 per-cell wall times and tool-call counts are published in `docs/c04-evidence/c04-aggregate-result.json`. Total observed wall time was `1,988,529.6 ms`; total tool-call count was `150`. No provider-billed cost claim is made because c04 did not preregister complete cost-coverage evidence.

## Durable evidence

- Freeze: `c07bf19`; exact post-freeze review and identity: `docs/c04-evidence/independent-review-8081-twins.md`, `independent-review-8081-twins-session.jsonl`, and `independent-review-8081-twins-identity.md`.
- Zero-materialization preflight: `docs/c04-evidence/preflight-c04-off-r1-yaml-markdown.json`.
- Mechanical aggregate and all 24 paired cells: `docs/c04-evidence/c04-aggregate-result.json`.
- Final 48-run ledger: `docs/c04-evidence/raw-publication-ledger.json`.
- Full raw bundles: `docs/c04-raw/c04-*/`.
- Publication verification: `docs/c04-evidence/raw-publication-verification.txt` proves 1,008 source files have tracked byte-identical copies and every evidence manifest verifies.

The guard remains default-off. No c04 retry, narrower reinterpretation, provider/model substitution, or rollout is authorized. c01, c02, and c03 remain separate historical no-uplift evidence.
