// Context vector extraction module — distills session history into 9 strategic context vectors.

import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ExtractedContext } from "./types.js";
import type { ModelCallFn } from "./core.js";

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
  '  "observedWork": ["High-level milestone progress achieved so far (do NOT list individual tool calls)"],',
  '  "observedCriticalFacts": ["Verified domain truths, system behaviors, and test outcomes observed in logs"],',
  '  "relevantLearnings": ["Systemic insights, structural architecture patterns, or project rules learned"],',
  '  "deliberationNeeded": true or false,',
  '  "deliberationReason": "Short reason explaining why full probe deliberation is or is not needed"',
  "}",
  "",
  "Set deliberationNeeded to true if code/files were modified without test verification, if requirements are AMBIGUOUS, if tools failed critically, or if the user asked a complex architectural question.",
  "Set deliberationNeeded to false if the user input is a simple acknowledgment, status check, routine question, or clear step in progress with fresh evidence.",
  "",
  "Output raw JSON ONLY. No conversational prefix or markdown wrapper.",
].join("\n");

/** Safe default fallback context when extraction is skipped or fails. */
export function getDefaultExtractedContext(messages?: AgentMessage[]): ExtractedContext {
  let initialGoal = "General task execution";
  if (messages && messages.length > 0) {
    const firstUserMsg = messages.find((m) => m.role === "user");
    if (firstUserMsg && "content" in firstUserMsg && typeof firstUserMsg.content === "string") {
      initialGoal = firstUserMsg.content.slice(0, 200);
    }
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

/** Extract 9 strategic context vectors from recent messages using a fast LLM pass. */
export async function extractContextFromMessages(
  messages: AgentMessage[],
  callModel: ModelCallFn,
  previousContext?: ExtractedContext,
  signal?: AbortSignal,
): Promise<ExtractedContext> {
  if (messages.length === 0) {
    return getDefaultExtractedContext(messages);
  }

  const formattedHistory = messages
    .slice(-10)
    .map((m) => {
      const role = String(m.role).toUpperCase();
      let content = "";
      if ("command" in m && "output" in m && typeof m.output === "string") {
        content = `> ${(m as any).command}\n${(m as any).output.slice(0, 500)}`;
      } else if ("content" in m) {
        content = typeof (m as any).content === "string" ? (m as any).content : JSON.stringify((m as any).content);
      }
      return `[${role}] ${content.slice(0, 1000)}`;
    })
    .join("\n\n");

  let userPrompt = `Conversation History:\n\n${formattedHistory}`;
  if (previousContext) {
    userPrompt = `Previous Extracted Context Baseline:\n${JSON.stringify(previousContext, null, 2)}\n\n${userPrompt}`;
  }

  try {
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
    };
  } catch {
    return getDefaultExtractedContext(messages);
  }
}
