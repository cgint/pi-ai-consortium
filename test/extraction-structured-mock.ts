import type { ModelCallResponse } from "../src/core.js";
import type { ExtractedContext } from "../src/types.js";

/** Build the strict AX output-function response used by extraction tests. */
export function extractionStructured(ctx: Partial<ExtractedContext> & { probeContribution?: string } = {}): ModelCallResponse {
  return {
    text: "",
    functionCalls: [{
      id: "test-ax-output",
      name: "__axOutput",
      arguments: {
        userRequirements: ctx.userRequirements ?? [],
        deliverables: ctx.deliverables ?? [],
        revisedOrSupersededDirection: ctx.revisedOrSupersededDirection ?? [],
        userDecisions: ctx.userDecisions ?? [],
        questionsAndInformationGaps: ctx.questionsAndInformationGaps ?? [],
        controlBoundaries: ctx.controlBoundaries ?? [],
        observedWork: ctx.observedWork ?? [],
        observedCriticalFacts: ctx.observedCriticalFacts ?? [],
        relevantLearnings: ctx.relevantLearnings ?? [],
        deliberationNeeded: ctx.deliberationNeeded ?? true,
        ...(ctx.deliberationReason !== undefined ? { deliberationReason: ctx.deliberationReason } : {}),
        ...(ctx.activeHumanInputSourceIds !== undefined ? { activeHumanInputSourceIds: ctx.activeHumanInputSourceIds } : {}),
        ...(ctx.supersededHumanInputSourceIds !== undefined ? { supersededHumanInputSourceIds: ctx.supersededHumanInputSourceIds } : {}),
        probeContribution: ctx.probeContribution ?? "",
      },
    }],
  };
}
