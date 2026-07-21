# Probe Behavior Issues — Observed Failures

**As-of:** 2026-07-20  
**Status:** Investigation needed — root cause not yet identified

Three categories of systemic probe failure have been observed. All share a common theme: **the probes make confident judgments on incomplete or misleading context.**

---

## Issue 1: Premature judgment — probes fire before evidence exists

**Observed:** 2026-07-20 session `019f80db-c26bc`

User asked the agent to analyze a JSONL session file for timing differences. The consortium deliberation fired **before** the agent had read the file:

```
18:48:55  → User asks to analyze the JSONL file
18:48:57  → Consortium fires (2 seconds later)
18:49:05  → Agent starts reading the JSONL (8 seconds AFTER deliberation)
```

Clarifier issued BLOCK: *"The JSONL session file lacks the comparative baseline data..."*

The target JSONL contained 69 LLM calls with full timing data. The probes predicted impossibility without inspection.

**Root cause candidates:**
- Probes evaluate on the user prompt alone; they haven't seen the agent's tool results yet
- The deliberation hook fires at `context` event — before the agent has explored the data
- Probe instructions may not encourage "I can't judge yet" as a valid response

---

## Issue 2: Context layer confusion — embedded content mistaken for current actions

**Observed:** Session `019f80db-c26bc`, analyzing target file `11d788.jsonl`

The agent was reading a JSONL session file (`11d788.jsonl`). That JSONL contained records from a previous session where source code files were read. The navigator issued:

```
navigator (WARN): The agent has shifted focus from analyzing the specific session log
for timing differences to reading source code files, which does not directly
address the user's request to inspect the provided JSONL data.
synthesis: WARN: Shift back to analyzing the provided JSONL session logs for timing
differences instead of reading source code files.
```

The agent was exclusively reading the JSONL — every tool call targeted `11d788.jsonl`. Zero source code files were touched. The navigator saw source code paths inside the JSONL content and attributed them to the current agent.

The same pattern repeated across multiple deliberation rounds — the agent kept reading the JSONL (continuing from earlier offsets), and the consortium kept warning it to "stop reading source code" and "shift back to the JSONL."

**Root cause candidates:**
- Probe context flattens all visible text — no distinction between "agent is doing X" and "agent is reading a log that mentions X"
- Probe instructions don't account for meta-analysis scenarios (analyzing session logs, diffs, etc.)
- The `buildUserContextFromMessages` serialization embeds full tool result content, including file paths and source code, without framing

---

## Issue 3: Stale session state — probes react to constraints that no longer apply

**Observed:** Same session `019f80db-c26bc`

User disabled READ-ONLY mode (`--dm-read`), then instructed the agent to write a findings file. The agent complied. The consortium responded:

```
architect (BLOCK): The agent just saved a file (`findings-position-zero.md`) to disk
while in READ-ONLY mode, which violates the explicit `--dm-read` constraint set at
the start of this session.
navigator (BLOCK): The agent just wrote a fact-dump markdown file at the user's
instruction, then stopped — but the user's stated goal is to answer the question
"does the position-0 injection cause a slowdown?" The markdown file is a static
artifact, not an analysis or action that advances toward answering that question.
contrarian (WARN): The agent just wrote findings-position-zero.md but never verified
the contents are correct — the file contains unsubstantiated assertions...
synthesis: BLOCK: Saved `findings-position-zero.md` in READ-ONLY mode, violating the
`--dm-read` constraint.
```

The constraint had been removed moments earlier. Three of five probes contributed, all wrong. The synthesis amplified the architect's stale BLOCK into the dominant signal the agent received.

**Root cause candidates:**
- Probes receive session startup context but not runtime state transitions
- No mechanism for probes to detect discuss-mode changes
- Probe instructions reference session constraints as static facts rather than dynamic state

---

## Common thread: incomplete context representation → amplified harm

All three failures stem from how context is presented to the probes:

| Dimension | Problem | Effect |
|-----------|---------|--------|
| **Timing** | Probes fire before agent has gathered evidence | Premature impossible/invalid judgments |
| **Semantics** | No distinction between current actions and embedded historical records | False drift/off-task warnings |
| **State** | Session flags captured at startup, not refreshed at runtime | Stale constraint violations |
| **Expression** | One-sentence output format leaves no room for "insufficient information" | Forced confident judgments on thin evidence |

And the damage is compounded by the synthesis model. The synthesis prompt instructs: *"Surface only the single highest-severity signal."* This means a single wrong probe can dominate the output the agent receives. In Issue 3, three wrong probes produced a BLOCK synthesis that told the agent it violated a constraint that no longer existed — despite two probes correctly returning NO_CONTRIBUTION.

The harm chain:
```
Incomplete/stale probe context
  → Probe makes confident wrong judgment
    → Synthesis surfaces highest-severity (wrong) signal
      → Agent receives BLOCK/WARN guidance that contradicts reality
        → Agent wastes turns correcting or ignoring false signals
```

## Questions to investigate

1. **Probe context composition:** What exactly do probes receive? `buildUserContextFromMessages()` serializes the full message history — including tool results that embed file contents. Does this flatten meta-analysis scenarios (reading session logs that contain their own tool calls)?
2. **Deliberation timing:** The `context` event fires before the agent's first LLM call of the turn. On the initial turn, this means probes evaluate the user prompt alone — before the agent has explored any data. Can deliberation be deferred until after the agent has gathered initial evidence?
3. **Dynamic state:** How do probes learn about session state changes (mode switches, model changes, etc.)? The discuss-mode flag appears to be captured at session start and never refreshed. Is there a way to detect `discuss-mode disabled` events?
4. **Probe instructions:** Do the role lens prompts account for meta-analysis scenarios? Do they encourage epistemic humility when evidence is insufficient? The current gates ("If X is clear, return NO_CONTRIBUTION") assume the probe has enough information to decide — they don't handle "I can't tell yet."
5. **NO_CONTRIBUTION gate:** Is the gate calibrated to allow "I can't judge yet" as a valid non-contribution? Currently the only valid outputs are `NO_CONTRIBUTION` or a tagged observation. There is no middle ground for "insufficient evidence to form an opinion."
6. **Synthesis amplification:** The synthesis model surfaces the single highest-severity signal. This is dangerous when probes are operating on incomplete context — one wrong BLOCK drowns out four correct NO_CONTRIBUTIONs. Should synthesis weight signals by probe confidence, or require corroboration before surfacing BLOCK?

## Related code paths

- `src/context.ts` — `buildUserContextFromMessages()` serializes full message history into probe input (embeds tool results, file contents, source code)
- `index.ts` — `context` event handler triggers deliberation; `buildUserContext()` in `input` handler captures initial user text
- `src/config.ts` — probe role lens instructions, synthesis prompt ("surface only the single highest-severity signal")
- `src/core.ts` — `ConsortiumCore.deliberate()` orchestration; `validateProbeOutput()` enforcement
- `src/ui.ts` — `formatVisibleMessage()` renders consortium output to agent