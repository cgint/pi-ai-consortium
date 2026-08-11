# c02 preflight attempt 1 — infrastructure-invalid

**Status:** INVALID — zero prompts, no c02 runtime or harvested target materialized
**Run ID checked:** `c02-off-r1-yaml-markdown`

The preflight result is retained at `preflight-c02-off-r1-yaml-markdown.json`. It failed before Pi launch with:

```text
FileNotFoundError: /tmp/parcour-c02-off-r1-yaml-markdown/workspace/.pi/settings.json
```

`C02Runner._build_manifest()` reads the arm settings file before `_materialize_workspace()` is permitted to create it. This violates the c02 preflight-before-materialization contract. No prompt was delivered, and neither `/tmp/parcour-c02-off-r1-yaml-markdown` nor `.parcour-runs/c02-off-r1-yaml-markdown` exists.

This is infrastructure-invalid evidence only. It does not consume the c02 run ID, establish an OFF result, or authorize a source/harness correction. A corrected runner requires explicit amendment and a new prospective review/preflight sequence.
