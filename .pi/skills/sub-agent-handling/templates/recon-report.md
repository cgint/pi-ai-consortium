# RECON REPORT — the short return

This is the **inline** return, not the output file. Hard cap ~10 lines. The full
report goes to the output path; this exists so the main session knows whether it
must open it, and cannot miss a falsification.

```text
- Recon ID:      <nn-topic>
- Output:        <absolute path to the written report>
- Status:        complete | partial | premise-wrong
- HEADLINE:      <the single most decision-relevant fact, stated as a fact,
                  with file:line. Not "found several things".>
- CONTRADICTS:   <anything that falsifies the brief's premise, or NONE>
- NOT FOUND:     <load-bearing absences only>
- UNDETERMINED:  <what could not be settled, and why>
```

## Rules for filling it in

**`HEADLINE`** must be a fact a reader could act on or check, with a citation.

- Good: `evaluators/dspy.ex:14-24 defines 14 claim categories, incl.
  :open_question and :information_gap`
- Bad: `the claim system is more capable than expected`
- Bad: `completed successfully, see the file`

**`CONTRADICTS`** is the most important line. If the brief assumed something that
turned out false, it goes here — even when the run otherwise succeeded. A clean
run that overturns its own premise is the **most** valuable outcome, and it must
not be buried in the output file.

Write `NONE` only if the premise genuinely held. Do not leave it blank.

**`Status: premise-wrong`** is a legitimate, useful result. Prefer it over
quietly substituting a different task.

**`NOT FOUND`** lists only absences that were load-bearing. Do not restate every
negative answer; those belong in the output file.

**`UNDETERMINED`** must give the reason: source not readable, question needs a
running system, evidence conflicting, out of scope. "Unclear" alone is not an
answer.

## Why this shape

Measured 2026-07-25: the most valuable result of a five-scout run was that
`/inspect` emits 14 claim categories and **not** only `:permission`, falsifying a
belief this project had built on for days. Under a plain status line that would
have been invisible, and the summary would have been trusted without opening the
file. `CONTRADICTS` exists so that cannot happen again.
