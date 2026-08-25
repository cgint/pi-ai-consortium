// Context vector extraction module — distills session history into strategic context vectors.
// Uses @ax-llm/ax for typed signature, prompt rendering, and response validation.

import { ax, f } from "@ax-llm/ax";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ExtractedContext } from "./types.js";
import type { ModelCallFn } from "./core.js";
import { buildHumanInputFocus, buildObservedPastXml, getGenuineHumanInputs } from "./context.js";
import { AxPiService } from "./ax-pi-service.js";

/**
 * Policy instruction injected into the Ax signature's task definition.
 * The JSON schema and format instructions are owned by the Ax signature;
 * this text carries only the domain policy.
 */
export const EXTRACTION_INSTRUCTION = [
  "You are a high-level strategic context extraction engine for a software development agent.",
  "Analyze the conversation history and extract structured context vectors.",
  "",
  "CRITICAL FILTER RULE (Strategic Intent vs. Operational Friction):",
  "- FILTER OUT low-level operational mechanics and execution friction (e.g. edit tool line-number mismatches, transient bash error codes, tool parameter syntax typos, or intermediate search loops).",
  "- EXTRACT STRICTLY high-level strategic intent, macro goals, explicit user decisions, control boundaries, and domain facts.",
  "",
  "ACCUMULATION RULE:",
  "- If a PREVIOUS EXTRACTED CONTEXT is provided, PRESERVE and ACCUMULATE durable user intent, deliverables, user decisions, superseded directions, and control boundaries unless explicitly revoked or updated by the user.",
  "- Dynamically refresh observed work, critical facts, and information gaps based on recent evidence.",
  "",
  "Set deliberationNeeded to true only when the complete observed history contains a concrete, potentially helpful gap or risk that merits independent probes. A complex question alone is not sufficient.",
  "Set deliberationNeeded to false when no such signal exists; this means probes will not run, not merely that they should be brief.",
  "Human messages include source_id labels. The tail <human_input_focus> repeats the original and current genuine-human inputs for emphasis; the complete history remains the source of truth.",
  "Preserve the original mandate and current direction in the strategic vectors; select only active, genuinely useful source IDs for activeHumanInputSourceIds and mark replaced directions in supersededHumanInputSourceIds.",
].join("\n");

/** Ax signature for extraction — single source of truth for the 13 output fields. */
const extractionSignature = f()
  .input("history", f.string("Complete session history in XML format."))
  .input("stageTail", f.string("Stage-specific instructions and context appended after the complete history."))
  .output("userRequirements", f.string().array("Macro goals, acceptance criteria, quality expectations, and technical bounds"))
  .output("deliverables", f.string().array("Explicit required architectural artifacts, files, documentation, or reports expected"))
  .output("revisedOrSupersededDirection", f.string().array("Directions, goals, or constraints that were canceled, updated, or superseded"))
  .output("userDecisions", f.string().array("Explicit user choices, approved trade-offs, architecture selections, or preferences"))
  .output("questionsAndInformationGaps", f.string().array("High-level domain ambiguities or unaddressed user questions requiring clarification"))
  .output("controlBoundaries", f.string().array("Active session rules, allowed path boundaries, read-only mode flags, and session guards"))
  .output("observedWork", f.string().array("High-level milestone progress achieved so far (do not list individual tool calls)"))
  .output("observedCriticalFacts", f.string().array("Verified domain truths, system behaviors, and test outcomes observed in logs"))
  .output("relevantLearnings", f.string().array("Systemic insights, structural architecture patterns, or project rules learned"))
  .output("deliberationNeeded", f.boolean("True only when the history contains a concrete gap or risk that merits independent probes"))
  .output("deliberationReason", f.string("Short reason explaining why full probe deliberation is or is not needed").optional())
  .output("activeHumanInputSourceIds", f.string().array("source_id values for genuine human inputs whose exact wording should be emphasized to probes").optional())
  .output("supersededHumanInputSourceIds", f.string().array("source_id values for genuine human inputs superseded by later directions").optional())
  .output("probeContribution", f.string("For C3: exact NO_CONTRIBUTION or one tagged observation. For C1: an empty string.").optional())
  .useStructured()
  .build();

/**
 * Shared AX program for C1 extraction and C3 probes. Stage semantics belong in
 * `stageTail`, which follows the identical complete-history input.
 */
const extractionProgram = ax(extractionSignature, { maxRetries: 2 });
extractionProgram.setInstruction([
  "You are a Consortium deliberation stage.",
  "The complete observed history appears first. Follow only the stage-specific instructions that follow it.",
  "Return exactly one __axOutput function call matching the declared schema.",
].join("\n"));

export async function runStructuredDeliberationStage(
  callModel: ModelCallFn,
  modelKey: string,
  maxTokens: number,
  temperature: number,
  history: string,
  stageTail: string,
  signal?: AbortSignal,
) {
  const adapter = new AxPiService(callModel, modelKey, maxTokens, temperature);
  return extractionProgram.forward(adapter, { history, stageTail }, { abortSignal: signal });
}

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

/** Filter empty/whitespace-only strings from an array (light normalization). */
function cleanStringArray(arr: string[] | undefined): string[] {
  if (!Array.isArray(arr)) return [];
  return arr.filter((s) => s.trim().length > 0);
}

/**
 * Extract strategic context vectors from recent messages using a fast LLM pass.
 *
 * Uses @ax-llm/ax for typed signature, prompt rendering, and response validation.
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

  const history = buildObservedPastXml(messages);
  const baseline = previousContext
    ? (() => {
        const {
          activeHumanInputSourceIds: _active,
          supersededHumanInputSourceIds: _superseded,
          ...durable
        } = previousContext;
        return `<previous_extracted_context_baseline>\n${JSON.stringify(durable, null, 2)}\n</previous_extracted_context_baseline>`;
      })()
    : "";
  const stageTail = [
    "<c1_extraction_stage>",
    EXTRACTION_INSTRUCTION,
    baseline,
    buildHumanInputFocus(messages),
    "Set probeContribution to an empty string; it is used only by C3.",
    "</c1_extraction_stage>",
  ].filter((part) => part.length > 0).join("\n\n");

  // Run extraction through the shared AX transport: common history prefix → C1 tail → strict parse.
  const result = await runStructuredDeliberationStage(
    callModel,
    "extraction",
    1024,
    0.2,
    history,
    stageTail,
    signal,
  );

  return {
    userRequirements: cleanStringArray(result.userRequirements),
    deliverables: cleanStringArray(result.deliverables),
    revisedOrSupersededDirection: cleanStringArray(result.revisedOrSupersededDirection),
    userDecisions: cleanStringArray(result.userDecisions),
    questionsAndInformationGaps: cleanStringArray(result.questionsAndInformationGaps),
    controlBoundaries: cleanStringArray(result.controlBoundaries),
    observedWork: cleanStringArray(result.observedWork),
    observedCriticalFacts: cleanStringArray(result.observedCriticalFacts),
    relevantLearnings: cleanStringArray(result.relevantLearnings),
    deliberationNeeded: result.deliberationNeeded,
    deliberationReason: result.deliberationReason || undefined,
    activeHumanInputSourceIds: cleanStringArray(result.activeHumanInputSourceIds),
    supersededHumanInputSourceIds: cleanStringArray(result.supersededHumanInputSourceIds),
  };
}
