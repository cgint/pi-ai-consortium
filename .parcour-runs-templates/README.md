# Parcour Templates

Committed starting states for the courses we send agents through.

A **parcour** is the world an agent wakes up in: source files, documents, seeded defects — whatever marks the beginning of the course. Templates here are version-controlled so their hashes are reproducible from Git, which satisfies the fixture-hash requirement in the experimentation plan.

## Layout

```
<parcour-id>/
  parcour.json      metadata — NOT given to the agent
  workspace/        materialized into /tmp — the agent's entire visible world
```

Only `workspace/` is copied into the run directory. Everything at the template root is harness-side.

## Execution flow

```
.parcour-runs-templates/<id>/workspace/
        │  hash, copy
        ▼
/tmp/parcour-<run-id>/          agent runs here, sees nothing else
        │  harvest before /tmp is discarded
        ▼
<impl-repo>/.parcour-runs/<run-id>/    durable evidence, Git-ignored
```

Runs never execute inside a repository, and evidence never leaves the project.

## Rules for `workspace/` content

1. **Nothing may reveal that an experiment is running.** No `PREFLIGHT`, no `CONSORTIUM`, no `TEST_` markers, no references to evaluation, probes, or the extension under test. The course should read like ordinary work.
2. **No expected outcomes, assertions, or rubric hints.** The agent can read everything in `workspace/`. Anything describing what *should* happen belongs in the scenario definition in the concept repository, never here.
3. **No instructions to the agent.** Task instructions are scripted turns delivered by the runner. A workspace holds *materials*, not prompts.
4. **Marker values must look plausible.** When a course needs a verifiable token, use something a real project would contain (`RELEASE_TAG`, `BUILD_ID`), so the scorer-facing transcript needs no sanitizing rewrite.

## Separation of template and definition

| Artifact | Lives in | Seen by |
|---|---|---|
| Parcour template (`workspace/`) | this directory, committed | the agent |
| Scenario definition — scripted turns, expected consortium behavior, rubric expectations | concept repo `experiments/scenarios/` | the evaluator only |

Keeping them apart means the expected-behavior specification never sits inside a directory the agent can read.

## Metadata

`parcour.json` carries identity and a pointer to the scenario definition. It deliberately does **not** carry experimental parameters — tool allowlists, turn scripts, and expected behavior belong to the frozen scenario definition, not to the course materials.
