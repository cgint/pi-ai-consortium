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
  │  (architect)   │                 │   injection)  │
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

5 built-in probe roles:
- **Clarifier** — identifies ambiguities and missing information
- **Contrarian** — challenges assumptions and flags risks
- **Architect** — evaluates structural soundness and design choices
- **Navigator** — suggests what to read or investigate next
- **Responder** — assesses whether there's enough information to act

## Key design

- **Internal deliberation, not delegation.** Probes analyze; they don't spawn work. The final decision belongs to the synthesis stage.
- **NO_CONTRIBUTION protocol.** If a probe has nothing useful to add, it returns `NO_CONTRIBUTION`. If all probes return this, synthesis is skipped entirely.
- **Per-turn JSONL logging.** Every deliberation is logged immutably under `.pi/consortium/`. Timestamped filenames, append-only, never rotated, never deleted.
- **Blocking on `context` event.** Runs synchronously before each LLM call (including tool-call loops).

## Project structure (extension code)

```
index.ts           — extension entry point, Pi hooks
src/
  core.ts          — ConsortiumCore: probe orchestration, synthesis, validation
  types.ts         — ProbeConfig, TurnState, DeliberationResult interfaces
test/
  core.test.ts     — unit tests with mock model calls
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
