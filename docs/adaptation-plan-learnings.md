# Consortium Adaptation Plan: Evolutionary Refinements from Session Analysis

**Date:** 2026-07-23  
**Status:** Living Architectural Adaptation Plan (Subject to iterative updates based on session telemetry)  
**Target Repository:** `pi-ai-consortium`

---

## 1. Executive Intent

This document captures concrete architectural and behavioral adaptations for `pi-ai-consortium` derived from empirical session analysis (including session `019f8e11-c1ac-7054-8fe5-9cc583a54a75` and 10 repository trace logs in `.pi/consortium/`).

The core goal of these adaptations is to **maximize high-signal steering while eliminating unnecessary latency and friction during routine tool execution**.

---

## 2. Empirical Telemetry & Baseline Summary

Cross-session analysis of 10 repository trace logs reveals the following operational metrics:

* **Total Deliberations Analyzed:** 99 deliberations across 10 session files.
* **Injection Rate:** 6 injections (6.1%), 93 skipped (93.9%).
* **Intervention Categories (High Value):**
  1. *Tool Schema Error Recovery:* Injected schema fixes when tool calls failed validation.
  2. *Defect/Requirement Ambiguity:* Blocked action when user intent was insufficiently defined.
  3. *Evidence Freshness / Verification:* Warned when code or documentation files were edited without subsequent test or visual validation.
* **Latency Profile:** Each deliberation adds **1.5s – 2.0s** for Pass 1 (Context Extraction), and **2.5s – 4.5s** when full Pass 2 Probes + Pass 3 Synthesis execute.

---

## 3. Structural Adaptation Items

### Adaptation 1: Event-Driven & Tool-Type Deliberation Governor
* **Problem:** In session `019f8e11-c1ac-7054-8fe5-9cc583a54a75`, 16 out of 19 deliberations were Pass 1 extraction calls during sequential read-only tool calls (`read`, `bash ls`, `bash rg`). All 16 resulted in `injection_skipped`, adding ~30 seconds of pure latency.
* **Adaptation:** Introduce an **Event-Driven Deliberation Governor** prior to Pass 1 Context Extraction:
  * **Skip Deliberation (Fast Path):** Skip Pass 1 entirely if the previous tool call was a successful read-only operation (`read`, `search`, `find`, `ls`) AND no file write operations occurred since the last deliberation.
  * **Trigger Deliberation (Full Path):** Execute Pass 1 Context Extraction strictly on:
    1. New User Prompts (`input` event).
    2. Tool Execution Failures / Errors.
    3. Post-Write / Post-Edit Tool Completion (e.g. `edit`, `write`, `bash` command execution).

```
  EVENT / TOOL EVENT RECEIVED
             │
             ▼
  ┌─────────────────────────────────────┐
  │      DELIBERATION GOVERNOR          │
  └──────────────────┬──────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
   Is User Prompt OR         Is Successful Read Tool
   Write/Edit OR Tool Error?  & No Pending Edits?
        │                         │
        ▼                         ▼
  ┌───────────┐             ┌───────────┐
  │  RUN PASS 1│             │   SKIP    │
  │ EXTRACTION│             │DELIBERATION│
  └───────────┘             └───────────┘
```

---

### Adaptation 2: Category-Aware Verification Rules for Documentation vs Code
* **Problem:** Currently, the Contrarian probe treats OpenSpec documentation edits (`spec.md`, `tasks.md`, `design.md`) with the same verification strictness as production code edits, warning if tests/visual checks didn't immediately follow.
* **Adaptation:** Differentiate evidence freshness expectations by asset type:
  * **Production Code / Markup Changes (`.ts`, `.py`, `.html`, `.css`):** Require strict runtime test / visual proof before turn completion (Invariant I).
  * **Specification & Task Documentation (`openspec/`, `docs/`, `*.md`):** Allow documentation updates without flagging stale code test warnings unless precommit checks or structural linters are explicitly configured.

---

### Adaptation 3: Human Intent, Motive, & Values Alignment (Iterative Input Slot)
* **Status:** Open for User Input.
* **Objective:** Incorporate specific user constraints regarding human pairing dynamics, autonomy boundaries, and value alignment.
* **Placeholder Sections:**
  * *Motive Preservation:* Ensuring consortium does not prematurely push for code/test execution when the user is in pure ideation/documentation mode.
  * *Tone & Steering Balance:* Calibrating when a warning should be an explicit `BLOCK` versus a lightweight `HINT`.

---

## 4. Adaptation Roadmap & Next Steps

1. **Phase 1 (Immediate):** Implement the Event-Driven Deliberation Governor in `src/core.ts` / `index.ts` to skip redundant read-loop extractions.
2. **Phase 2 (User Feedback Integration):** Update Adaptation 3 based on direct user input regarding intent, motive, and values alignment.
3. **Phase 3 (Validation):** Re-run test suite and benchmark latency on multi-tool sessions.
