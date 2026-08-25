// Context vector extraction module — distills session history into 9 strategic context vectors.

import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ExtractedContext } from "./types.js";
import type { ModelCallFn } from "./core.js";
import { buildHumanInputFocus, buildObservedPastXml, getGenuineHumanInputs } from "./context.js";

export const EXTRACTION_SYSTEM_PROMPT = [
  "You are a high-level strategic context extraction engine for a software development agent.",
  "Analyze the conversation history and extract structured context vectors into JSON.",
  "",
  "CRITICAL FILTER RULE (Strategic Intent vs. Operational Friction):",
  "- FILTER OUT low-level operational mechanics and execution friction (e.g. edit tool line-number mismatches, transient bash error codes, tool parameter syntax typos, or intermediate search loops).",
  "- EXTRACT STRICTLY high-level strategic intent, macro goals, explicit user decisions, control boundaries, and domain facts.",
  "",
  "ACCUMULATION RULE:",
  "- If a PREVIOUS EXTRACTED CONTEXT is provided, PRESERVE and ACCUMULATE durable user intent, deliverables, user decisions, superseded directions, and control boundaries unless explicitly revoked or updated by the user.",
  "- Dynamically refresh observed work, critical facts, and information gaps based on recent evidence.",
  "",
  "Return JSON matching this schema exactly:",
  "{",
  '  "userRequirements": ["Macro goals, acceptance criteria, quality expectations, and technical bounds"],',
  '  "deliverables": ["Explicit required architectural artifacts, files, documentation, or reports expected"],',
  '  "revisedOrSupersededDirection": ["Directions, goals, or constraints that were canceled, updated, or superseded"],',
  '  "userDecisions": ["Explicit user choices, approved trade-offs, architecture selections, or preferences"],',
  '  "questionsAndInformationGaps": ["High-level domain ambiguities or unaddressed user questions requiring clarification"],',
  '  "controlBoundaries": ["Active session rules, allowed path boundaries, read-only mode flags, and session guards"],',
  '  "observedWork": ["High-level milestone progress achieved so far (do not list individual tool calls)"],',
  '  "observedCriticalFacts": ["Verified domain truths, system behaviors, and test outcomes observed in logs"],',
  '  "relevantLearnings": ["Systemic insights, structural architecture patterns, or project rules learned"],',
  '  "deliberationNeeded": true or false,',
  '  "deliberationReason": "Short reason explaining why full probe deliberation is or is not needed",',
  '  "activeHumanInputSourceIds": ["source_id values for genuine human inputs whose exact wording should be emphasized to probes"],',
  '  "supersededHumanInputSourceIds": ["source_id values for genuine human inputs superseded by later directions"]',
  "}",
  "",
  "Set deliberationNeeded to true only when the complete observed history contains a concrete, potentially helpful gap or risk that merits independent probes. A complex question alone is not sufficient.",
  "Set deliberationNeeded to false when no such signal exists; this means probes will not run, not merely that they should be brief.",
  "Human messages include source_id labels. The tail <human_input_focus> repeats the original and current genuine-human inputs for emphasis; the complete history remains the source of truth.",
  "Preserve the original mandate and current direction in the strategic vectors; select only active, genuinely useful source IDs for activeHumanInputSourceIds and mark replaced directions in supersededHumanInputSourceIds.",
  "",
  "Output raw JSON ONLY. No conversational prefix or markdown wrapper.",
].join("\n");

/**
 * Default context for the legitimate empty-history case (messages.length === 0).
 * NOT used as an error fallback — extraction errors propagate to core.ts.
 */
export function getDefaultExtractedContext(messages?: AgentMessage[]): ExtractedContext {
  let initialGoal = "General task execution";
  if (messages && messages.length > 0) {
    const firstHumanInput = getGenuineHumanInputs(messages)[0];
    if (firstHumanInput) initialGoal = firstHumanInput.content.slice(0, 200);
  }

  return {
    userRequirements: [initialGoal],
    deliverables: [],
    revisedOrSupersededDirection: [],
    userDecisions: [],
    questionsAndInformationGaps: [],
    controlBoundaries: ["Standard session rules"],
    observedWork: ["Session initialized"],
    observedCriticalFacts: ["Session history available in transcript"],
    relevantLearnings: [],
    deliberationNeeded: true,
    deliberationReason: "Default fallback context — full audit enabled by default",
    activeHumanInputSourceIds: [],
    supersededHumanInputSourceIds: [],
  };
}

/** Helper to ensure a parsed JSON property is a valid string array. */
function ensureStringArray(val: unknown, defaultVal: string[] = []): string[] {
  if (Array.isArray(val)) {
    return val.map((item) => String(item)).filter((s) => s.trim().length > 0);
  }
  if (typeof val === "string" && val.trim().length > 0) {
    return [val.trim()];
  }
  return defaultVal;
}

/**
 * Extract 9 strategic context vectors from recent messages using a fast LLM pass.
 *
 * Errors propagate to the caller (core.ts) which logs them and skips probes.
 * No silent fallback: a failed extraction must not masquerade as "nothing to extract".
 */
export async function extractContextFromMessages(
  messages: AgentMessage[],
  callModel: ModelCallFn,
  previousContext?: ExtractedContext,
  signal?: AbortSignal,
): Promise<ExtractedContext> {
  if (messages.length === 0) {
    return getDefaultExtractedContext(messages);
  }

  let userPrompt = buildObservedPastXml(messages);

  if (previousContext) {
    const {
      activeHumanInputSourceIds: _activeHumanInputSourceIds,
      supersededHumanInputSourceIds: _supersededHumanInputSourceIds,
      ...durablePreviousContext
    } = previousContext;
    userPrompt = `${userPrompt}\n\n<previous_extracted_context_baseline>\n${JSON.stringify(durablePreviousContext, null, 2)}\n</previous_extracted_context_baseline>`;
  }
  userPrompt = `${userPrompt}\n\n${buildHumanInputFocus(messages)}`;

  const raw = await callModel(
    "extraction",
    EXTRACTION_SYSTEM_PROMPT,
    userPrompt,
    1024,
    0.2,
    signal,
  );

  const jsonText = raw.replace(/^```(?:json)?\n?/i, "").replace(/\n?```$/i, "").trim();
  const parsed = JSON.parse(jsonText);
  const defaults = getDefaultExtractedContext(messages);

  return {
    userRequirements: ensureStringArray(parsed.userRequirements, defaults.userRequirements),
    deliverables: ensureStringArray(parsed.deliverables, defaults.deliverables),
    revisedOrSupersededDirection: ensureStringArray(parsed.revisedOrSupersededDirection, defaults.revisedOrSupersededDirection),
    userDecisions: ensureStringArray(parsed.userDecisions, defaults.userDecisions),
    questionsAndInformationGaps: ensureStringArray(parsed.questionsAndInformationGaps, defaults.questionsAndInformationGaps),
    controlBoundaries: ensureStringArray(parsed.controlBoundaries, defaults.controlBoundaries),
    observedWork: ensureStringArray(parsed.observedWork, defaults.observedWork),
    observedCriticalFacts: ensureStringArray(parsed.observedCriticalFacts, defaults.observedCriticalFacts),
    relevantLearnings: ensureStringArray(parsed.relevantLearnings, defaults.relevantLearnings),
    deliberationNeeded: typeof parsed.deliberationNeeded === "boolean" ? parsed.deliberationNeeded : true,
    deliberationReason: parsed.deliberationReason ? String(parsed.deliberationReason) : undefined,
    activeHumanInputSourceIds: ensureStringArray(parsed.activeHumanInputSourceIds),
    supersededHumanInputSourceIds: ensureStringArray(parsed.supersededHumanInputSourceIds),
  };
}
