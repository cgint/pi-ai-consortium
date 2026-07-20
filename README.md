# pi-ai-consortium

Multi-model deliberation engine for Pi coding agent. Part of the **Deliberate Agent** federation.

> **Charter:** [`../deliberate-agent/CHARTER.md`](../deliberate-agent/CHARTER.md)  
> **Concept docs:** [`../concepts/pi-ai-consortium/`](../concepts/pi-ai-consortium/)

## What it does

The consortium adds **pre-generation deliberation** to Pi: before the agent model generates a response, multiple independent probes analyze the conversation state from different angles. A synthesis model absorbs their outputs and injects a refined prompt into the agent's context.

```
LLM history + new input
         │
         ▼
  ┌──────────────┐     Divergence    ┌──────────────┐
  │  Probe 1      │ ───────────────► │   Synthesis   │
  │  (clarifier)   │                 │    (merges    │
  │  Probe 2      │                 │   probe out-  │
  │  (contrarian)  │ ───────────────► │   puts and    │
  │  Probe 3      │                 │   decides     │
  │  (architect)   │ ───────────────► │   injection)  │
  │  Probe 4      │ ───────────────► │              │
  │  (navigator)   │                 │              │
  │  Probe 5      │                 │              │
  │  (responder)   │ ───────────────► │              │
  └──────────────┘                    └──────┬───────┘
                                             │
                                             ▼
                                    refined input
                                    → agent LLM call
```

5 built-in probe roles (alphabetical):
- **Architect** — evaluates structural soundness and design choices
- **Clarifier** — identifies ambiguities and missing information
- **Contrarian** — challenges assumptions and flags risks
- **Navigator** — suggests what to read or investigate next
- **Responder** — assesses whether there's enough information to act

## Key design

- **Internal deliberation, not delegation.** Probes analyze; they don't spawn work. The final decision belongs to the synthesis stage.
- **NO_CONTRIBUTION protocol.** If a probe has nothing useful to add, it returns `NO_CONTRIBUTION`. If all probes return this, synthesis is skipped entirely.
- **Per-turn JSONL logging.** Every deliberation is logged immutably under `.pi/consortium/`. Timestamped filenames, append-only, never rotated, never deleted.
- **Blocking on `context` event.** Runs synchronously before each LLM call (including tool-call loops).

## TUI visibility

The consortium reports live progress in the Pi status bar during deliberation:

```
consortium: 1/5 architect… → 2/5 clarifier… → … → synthesizing… → ✓ complete
```

After deliberation, a notification line appears in the TUI chat showing each probe's output and the synthesis:

```
◇ Consortium deliberation — 3/5 probes contributed
  architect: NO_CONTRIBUTION
  clarifier (WARN): Agent is drifting into file organization instead of fixing the bug.
  contrarian (BLOCK): Current approach will break existing tests.
  navigator: NO_CONTRIBUTION
  responder: NO_CONTRIBUTION
  synthesis: Run tests before committing — current approach risks breaking existing test suite.
```

If all probes return `NO_CONTRIBUTION`, the status bar shows `⏭ skipped (nothing to add)`.

## Project structure (extension code)

```
index.ts           — extension entry point (Pi hooks, ~170 lines)
src/
  config.ts        — DEFAULT_CONFIG, PROBE_SYSTEM_PROMPT, probe definitions
  context.ts       — buildUserContext, buildUserContextFromMessages
  core.ts          — ConsortiumCore: probe orchestration, synthesis, validation
  model.ts         — model invocation with auth forwarding
  types.ts         — ProbeConfig, TurnState, DeliberationResult, ProgressCallback
  ui.ts            — TUI formatting, ConsortiumLogger, progress callback factory
test/
  core.test.ts     — unit tests with mock model calls
  model.test.ts    — model auth tests
  progress.test.ts — progress callback tests (serial, parallel, error resilience)
```

## Quick start (development)

```bash
npm install
npx vitest run       # run tests
npx tsc --noEmit     # type-check
```

## Relationship to sibling projects

| Project | Role | Link |
|---------|------|------|
| pi-supervisor-guide | Live session observer, owns trace schema | `../pi-supervisor-guide/` |
| coding-workflow-orchestration | Phase policy from real sessions | `../coding-workflow-orchestration/` |
| pi-self-reflect | Mid-turn reflection sensor | `../pi-self-reflect/` |
| driver-copilot | Side-channel session watcher | `../pi-sessions-replace-driver/` |

This project is the **deliberation engine** — it reads trace state and phase decisions from the ecosystem and produces refined input or next-action proposals. It does not host or absorb sibling projects.

## License

ISC