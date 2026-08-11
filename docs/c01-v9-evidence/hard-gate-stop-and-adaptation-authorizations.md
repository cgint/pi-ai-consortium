# c01 C19 hard-gate stop and adaptation authorization record

**Status:** Historical control record — no adaptation is retained

## Hard-gate stop

A1b completed with valid runtime identity and failed C19 (`yaml_historical=False`). The c01 serial matrix stopped immediately: D1, A2, D2, A3, and D3 were not run; D5 and D7 were not derived. The live-run result is tracked at `a1b-result.json`.

The goal was paused at that point with the C19 result and a request for user direction. No frozen c01 cell was retried, substituted, or changed after this stop.

## Explicit post-stop authorizations

1. The user requested a read-only review and recommendation, then stated: **“i go with your recommendation and authorize”**. This authorized isolated candidate 1 only; it did not authorize another frozen c01 run.
2. After candidate 1’s invalid closure, the user stated: **“If something went wrong, omit it and do it in the right way again.”** Candidate 2 was separately preregistered, local-only, and isolated.
3. After candidate 2’s mechanism-inconclusive closure, the user stated: **“i authorize you to proceed with logic and smart ways to provide HONEST progress”**. The correct evidence-preserving decision was not to consume a third candidate: no candidate can turn frozen A1b’s C19 failure into a passing frozen matrix.

## Boundary

Candidates 1 and 2 are recorded as invalid and mechanism-inconclusive respectively. They did not repair, replace, reinterpret, or supply D5/D7 evidence for frozen c01. Their unconsumed second run IDs remain unused. The final disposition is the no-uplift stop published in `../c01-v9-final-no-uplift-outcome.md`.
