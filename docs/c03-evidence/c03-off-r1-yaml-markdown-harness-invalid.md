# c03-off-r1-yaml-markdown — harness-invalid stop

**Status:** INVALID — first c03 cell consumed; matrix stopped

The runtime identity was correct:

- `state_final.json` records `data.model.provider: "8081-twins"`, `data.model.id: "qwen36-27b-nvidia-nvfp4"`, and `data.thinkingLevel: "off"`.
- The raw session `model_change` records provider `8081-twins` and model ID `qwen36-27b-nvidia-nvfp4`.
- All six consortium `deliberation_start` records use `8081-twins/qwen36-27b-nvidia-nvfp4` from `CONSORTIUM_MODEL`.

The frozen runner incorrectly validates executor provider/model at `get_state.data.provider` and `get_state.data.modelId`; Pi `0.84.1` returns those values under `get_state.data.model.provider` and `.id`. Consequently `C03-executor-provider` and `C03-executor-model` failed with `initial=None; final=None`, and the runner returned mandatory-stop exit code `2`.

The process exited `0`, delivered three prompts, and descriptively passed continuity, but the cell is harness-invalid under the frozen protocol. It is not a valid OFF observation. No later c03 cell, retry, source correction, or ID substitution is authorized.
