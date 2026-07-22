# North Star & Philosophy: Beyond "Just the LLM Call"

**As-of:** 2026-07-22  
**Status:** Living Architectural Foundation  
**System Scope:** `pi-ai-consortium` (Part of the Deliberate Agent Federation)

---

## 1. The Core Problem: Single-Call Fragility

When an AI coding agent operates as a single LLM execution loop, it suffers from predictable cognitive traps:

1. **Synthetic Confidence & Sycophancy Loops:** Resolving code-review comments or getting praise from review bots creates a false sense of completion ("It compiled, the bot praised me, merge time!").
2. **Stale Evidence Blindness:** The agent modifies code *after* taking a screenshot or running a test, but assumes the old evidence still proves the new code works.
3. **Eager Completion Drift & Action Momentum:** When faced with template checklists or execution tools, the model jumps straight to Phase 2 (Action) without checking if the action serves the user's high-level goal.
4. **Context Decay:** Over long sessions, rules at the top of the context window lose attention weight, causing the agent to forget governance and verification boundaries.

---

## 2. The Core Solution: Multi-Perspective Deliberation

> **"Every step must be more than 'just an LLM call'—it must be a system that deliberates from distinct, independent perspectives before action occurs."**

`pi-ai-consortium` intercepts the agent *before* it generates a response or executes a tool call. By fanning out the conversation context to multiple independent **Probe Roles**, it forces the system to interrogate its own assumptions from diverse viewpoints:

```
  SINGLE LLM CALL (Vulnerable to Sycophancy)
  ┌────────────────────────────────────────────────────────┐
  │ LLM → "Code fixed! Sheldon praised me! Merging now!"  │  ❌ Single failure point
  └────────────────────────────────────────────────────────┘

  CONSORTIUM DELIBERATION (Multi-Perspective Filter)
  ┌──────────────────┐
  │  Agent Context   │
  └────────┬─────────┘
           │
           ├──► Probe 1: RESPONDER   ──► "Is information sufficient and goal active?"
           ├──► Probe 2: CONTRARIAN  ──► "Wait! HTML was edited AFTER screenshot! Evidence is stale!"
           ├──► Probe 3: CLARIFIER   ──► "Agent is flattering review bot instead of showing visual proof!"
           ├──► Probe 4: ARCHITECT   ──► "Is structural design sound or is this a superficial hack?"
           └──► Probe 5: NAVIGATOR   ──► "What concrete evidence or read is missing before acting?"
           │
           ▼
  ┌──────────────────┐     Spectrum Probe Output
  │    SYNTHESIS     │  ─────────────────────────────────► Inject Hard Gate/Warning into Agent Input:
  └──────────────────┘                                      "BLOCK: Take fresh screenshot before MR update!"
```

---

## 3. The Anti-Sycophancy & Grounding Invariants

To guarantee that the agent remains grounded in live reality, probe roles evaluate the conversation against three hard invariants:

### Invariant I: Code Edits Invalidate Visual Evidence
If HTML, CSS, or JS files are modified *after* a screenshot or visual proof was captured, the previous evidence is declared **stale and void**. Probes emit a `BLOCK` or `WARN` forcing a fresh runtime capture before any handoff or MR update.

### Invariant II: Cold, Un-Sycophantic Communication
Communication with review bots (e.g. `@ai-sheldon`) must be stripped of flattery and synthetic praise (*"brilliant"*, *"phenomenal"*, *"100% green"*). Probes flag sycophantic echo chambers and demand cold, factual diff pointers and un-stale test logs.

### Invariant III: Action as an Information Probe (3-Phase Loop)
Every action must follow the **3-Phase Knowledge Loop**:
1. **Observe & Orient (Phase 1):** Inspect the environment, understand constraints, and check goals.
2. **Bounded Action as Probe (Phase 2):** Execute a small, surgical action specifically to test runtime reality.
3. **Step Back & Re-Evaluate (Phase 3):** Stop immediately after the action to inspect the output and verify whether reality matches expectations.

---

## 4. The 4 Cs Framework for Deliberation

The consortium enforces the **4 Cs Framework** on every turn:

* **Context:** Probes reconstruct the active, unsuperseded goal rather than naively grabbing the latest user turn.
* **Communication:** Probes strip conversational filler and force concise, high-signal reasoning.
* **Collaboration:** Probes respect strict ownership boundaries—`[User Verification]` tasks and final merge triggers belong exclusively to the human user.
* **Clarity:** Probes demand explicit confidence calibration and surface unverified hypotheses explicitly instead of papering over gaps.

---

## 5. Summary

The Consortium turns the agent from a hasty, sycophantic code generator into a **Deliberate Engineering Partner**. By forcing multi-perspective deliberation before every turn, we ensure that actions are grounded in fresh, observable evidence rather than optimistic assumptions.
