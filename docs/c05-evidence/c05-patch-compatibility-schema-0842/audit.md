# c05 Pi 0.84.2 compatibility schema probe

**Status:** PASS — compatibility evidence only; not a Phase 0 retry and not behavioral evidence.

- Fresh ID: `c05-patch-compatibility-schema-0842`
- Runtime: Pi `0.84.2`, Node `v22.23.2`
- RPC controls: exactly two `get_state` commands; zero prompt commands
- Initial and final nested state: provider `8081-twins`, model `qwen36-27b-nvidia-nvfp4`, thinking `off`
- Process exit: `0`; failure: `null`
- All 13 recorded checks passed, including extension hashes, confinement, exact settings, explicit reviewer command, publication dry-run, nested identities, and process completion.

`result.json` and `console.json` are byte-identical copies of the one-time runtime artifacts. `probe-wrapper.py` assigns a fresh ID/workspace/evidence destination and invokes the already tested control-only `c05_phase0_probe.run_live()` implementation; it does not alter accepted Phase 0-B paths.
