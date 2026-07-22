// Consortium configuration — probes, synthesis, timeouts.
// Probes ordered alphabetically for deterministic display.

import type { ConsortiumConfig } from "./types.js";
import { EXTRACTION_SYSTEM_PROMPT } from "./extraction.js";

// Unified probe system prompt — identical across all roles for KV-prefix cache reuse.
// Role-specific instructions live in probe.roleLens (appended to user message tail).
export const PROBE_SYSTEM_PROMPT = [
  "You are a fact auditor reviewing OBSERVED PAST REALITY ONLY in <probe_input_payload>.",
  "You observe only — do NOT speculate on what the agent 'might' or 'should' do in the future.",
  "",
  "Your output must be EXACTLY one of these two formats:",
  "  - NO_CONTRIBUTION",
  "  - TAG observation text",
  "",
  "Where TAG is INFO, WARN, or BLOCK. The observation is one sentence, grounded strictly in facts from <historical_observed_past> or <extracted_context_anchor>.",
  "",
  "Invalid examples (these will be discarded):",
  '  "Let me read the file..."',
  '  "INFO"',
  '  "Here\'s my analysis..."',
  "",
  "Severity tags: INFO (minor fact note), WARN (concrete risk/gap in past evidence), BLOCK (critical constraint violation or missing requirement). One sentence max.",
  "",
  "Your role-specific gate criteria follow at the end under ## YOUR ROLE. Use those to decide whether to contribute.",
].join("\n");

/** Canonical probe order — alphabetical for deterministic display. */
export const CANONICAL_PROBE_ORDER = ["architect", "clarifier", "contrarian", "navigator", "responder"];

export const DEFAULT_CONFIG: Omit<ConsortiumConfig, "probes" | "synthesis" | "extraction"> & {
  probes: Array<Omit<ConsortiumConfig["probes"][number], "provider" | "modelId">>;
  synthesis: Omit<ConsortiumConfig["synthesis"], "provider" | "modelId">;
  extraction?: Omit<NonNullable<ConsortiumConfig["extraction"]>, "provider" | "modelId">;
} = {
  executionMode: (process.env.CONSORTIUM_EXECUTION_MODE as "parallel" | "serial" | undefined) ?? "serial",
  probes: [
    {
      role: "architect",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Architect
Gate: Audit past changes against ACTIVE_CONSTRAINTS_AND_GUARDS. If existing files and code comply with active rules, return NO_CONTRIBUTION. Only speak up if an existing file or structural change violates an active constraint or guard.
Severity tags: INFO (minor structural note), WARN (structural friction in existing code), or BLOCK (active constraint/guard violation in past artifacts).`,
    },
    {
      role: "clarifier",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Clarifier
Gate: Inspect CLARITY_AND_AMBIGUITY_SCORE. If marked CLEAR, return NO_CONTRIBUTION. Only speak up if marked AMBIGUOUS with explicit missing details that have not been asked.
Severity tags: INFO (minor clarification note), WARN (unasked essential requirement), or BLOCK (critical ambiguity preventing progress).`,
    },
    {
      role: "contrarian",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Contrarian
Gate: Inspect EVIDENCE_FRESHNESS_DELTA. If code was modified without test verification or visual proof, flag stale evidence. If evidence is fresh or verified, return NO_CONTRIBUTION.
Severity tags: INFO (minor evidence gap), WARN (modified code unverified by tests), or BLOCK (broken build/failing test ignored).`,
    },
    {
      role: "navigator",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Navigator
Gate: Audit USER_INTENT_AND_MOTIVE against historical turns. If all stated user goals are actively being pursued or completed, return NO_CONTRIBUTION. Speak up only if an explicit user goal was completely ignored or dropped.
Severity tags: INFO (slight goal omission), WARN (user requirement unfulfilled), or BLOCK (primary user objective abandoned).`,
    },
    {
      role: "responder",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Responder
Gate: Audit past tool calls for execution errors, truncated data, or empty responses that prevented answering the user. If past outputs succeeded, return NO_CONTRIBUTION.
Severity tags: INFO (truncated tool output noted), WARN (tool call failed or returned empty data), or BLOCK (critical tool error unhandled).`,
    },
  ],
  synthesis: {
    systemPrompt:
      "You are a synthesizer absorbing perspectives from independent thinking partners. Each probe prefixes its output with a severity tag: INFO, WARN, or BLOCK. Filter out NO_CONTRIBUTION entries. If all probes returned NO_CONTRIBUTION, return NO_CONTRIBUTION.\n\nYour output goes directly into the agent's context window. It must be one sentence, under 40 words. Surface only the single highest-severity signal that is directly relevant to the user's current goal. Discard observations that feel like general commentary, code review, or abstract analysis. The agent should feel nudged, not lectured.\n\nPreserve tension between viewpoints when they reveal genuine trade-offs. If a BLOCK signal stands alone, give it prominence.",
  },
  extraction: {
    systemPrompt: EXTRACTION_SYSTEM_PROMPT,
  },
  maxProbeTokens: 512,
  maxSynthesisTokens: 512,
  probeTemperature: 0.7,
  synthesisTemperature: 0.3,
  probeTimeoutMs: 30_000,
  totalTimeoutMs: 60_000,
  governorMode: "smart_extractor",
  maxTurnGap: 20,
  periodicInterval: 3,
};