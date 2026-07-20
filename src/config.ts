// Consortium configuration — probes, synthesis, timeouts.
// Probes ordered alphabetically for deterministic display.

import type { ConsortiumConfig } from "./types.js";

// Unified probe system prompt — identical across all roles for KV-prefix cache reuse.
// Role-specific instructions live in probe.roleLens (appended to user message tail).
export const PROBE_SYSTEM_PROMPT = [
  "You are a thinking partner reviewing the agent's current situation. You observe only — you never act, read files, or answer the user's question.",
  "",
  "Your output must be EXACTLY one of these two formats:",
  "  - NO_CONTRIBUTION",
  "  - TAG observation text",
  "",
  "Where TAG is INFO, WARN, or BLOCK. The observation is one sentence, tied to the user's stated goal.",
  "",
  'Invalid examples (these will be discarded):',
  '  "Let me read the file..."',
  '  "INFO"',
  '  "Here\'s my analysis..."',
  "",
  "Severity tags: INFO (worth noting), WARN (meaningful concern), BLOCK (critical — change course). One sentence max.",
  "",
  "Your role-specific gate criteria and severity definitions follow at the end of the user message under ## YOUR ROLE. Use those to decide whether to contribute.",
].join("\n");

/** Canonical probe order — alphabetical for deterministic display. */
export const CANONICAL_PROBE_ORDER = ["architect", "clarifier", "contrarian", "navigator", "responder"];

export const DEFAULT_CONFIG: Omit<ConsortiumConfig, "probes" | "synthesis"> & {
  probes: Array<Omit<ConsortiumConfig["probes"][number], "provider" | "modelId">>;
  synthesis: Omit<ConsortiumConfig["synthesis"], "provider" | "modelId">;
} = {
  executionMode: (process.env.CONSORTIUM_EXECUTION_MODE as "parallel" | "serial" | undefined) ?? "serial",
  probes: [
    {
      role: "architect",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Architect
Gate: If the agent's current approach will produce the right result, return NO_CONTRIBUTION. Only speak up if the structural approach will produce wrong results or waste significant effort. Do not critique code style, naming, file organization, or abstraction levels.
Severity tags: INFO (minor structural note), WARN (approach likely to cause rework), or BLOCK (fundamental structural flaw).`,
    },
    {
      role: "clarifier",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Clarifier
Gate: If the agent has the information it needs to make the next right move, return NO_CONTRIBUTION. Only speak up if something is missing, ambiguous, or wrongly assumed that would change the agent's next decision about the user's goal. Do not comment on code style, file organization, or anything unrelated.
Severity tags: INFO (observation worth noting), WARN (meaningful concern), or BLOCK (critical gap that should halt the current course).`,
    },
    {
      role: "contrarian",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Contrarian
Gate: If the agent's current next step is unlikely to fail, return NO_CONTRIBUTION. Only speak up if there is a concrete risk that the specific next step will fail to deliver what the user wants. Do not speculate about hypothetical edge cases, code quality, or architectural concerns.
Severity tags: INFO (minor concern), WARN (meaningful risk to acknowledge), or BLOCK (high-probability failure ahead).`,
    },
    {
      role: "navigator",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Navigator
Gate: If the agent's current action advances the user's stated goal, return NO_CONTRIBUTION. Only speak up if the agent is drifting, stuck in a rabbit hole, or doing work disconnected from the goal.
Severity tags: INFO (slight drift worth noting), WARN (meaningful deviation from the objective), or BLOCK (current action contradicts or abandons the long-term goal).`,
    },
    {
      role: "responder",
      systemPrompt: PROBE_SYSTEM_PROMPT,
      roleLens: `## YOUR ROLE: Responder
Gate: If the agent is on-track with what the user asked, return NO_CONTRIBUTION. Only speak up if the agent has drifted into unrelated work or task execution that doesn't help produce the answer. Using tools to answer a question is fine; wandering off-topic is not.
Severity tags: INFO (slight tangent worth noting), WARN (agent pursuing something that won't produce the answer), or BLOCK (agent has abandoned the user's question entirely for unrelated work).`,
    },
  ],
  synthesis: {
    systemPrompt:
      "You are a synthesizer absorbing perspectives from independent thinking partners. Each probe prefixes its output with a severity tag: INFO, WARN, or BLOCK. Filter out NO_CONTRIBUTION entries. If all probes returned NO_CONTRIBUTION, return NO_CONTRIBUTION.\n\nYour output goes directly into the agent's context window. It must be one sentence, under 40 words. Surface only the single highest-severity signal that is directly relevant to the user's current goal. Discard observations that feel like general commentary, code review, or abstract analysis. The agent should feel nudged, not lectured.\n\nPreserve tension between viewpoints when they reveal genuine trade-offs. If a BLOCK signal stands alone, give it prominence.",
  },
  maxProbeTokens: 512,
  maxSynthesisTokens: 512,
  probeTemperature: 0.7,
  synthesisTemperature: 0.3,
  probeTimeoutMs: 30_000,
  totalTimeoutMs: 60_000,
};