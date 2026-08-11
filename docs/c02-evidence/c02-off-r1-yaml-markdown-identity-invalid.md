# c02-off-r1-yaml-markdown — identity-invalid stop

**Status:** INVALID — matrix stopped after the first consumed c02 cell

The cell delivered all three prompts and its Pi process exited `0`, but the required deliberation identity gate failed. The raw consortium trace records `model: "google/gemini-3.5-flash"` with `modelSource: "CONSORTIUM_MODEL"` on every `deliberation_start` (for example `docs/c02-raw/c02-off-r1-yaml-markdown/consortium/*.jsonl:2`). This violates c02’s required local execution identity `olla/qwen36-27b-nvidia-nvfp4`.

`result.json` records `C02-trace-identity` failed, six deliberation starts, three delivered prompts, process return code `0`, and no runner exception. Continuity was true descriptively, but it is not interpretable c02 evidence because the identity gate failed.

The frozen matrix stops here. All later c02 IDs remain unconsumed; no cell retry, model substitution, or source correction is authorized by this result.
