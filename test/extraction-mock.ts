/**
 * Helper to build Ax labeled-field extraction responses for tests.
 *
 * Ax's prompt-based (non-structured-output) mode expects one
 * `Display Name: value` line per output field. Arrays are JSON-encoded,
 * booleans are bare, and the single string field (deliberationReason)
 * is unquoted.
 */
import type { ExtractedContext } from "../src/types.js";

export function extractionLabeled(ctx: Partial<ExtractedContext> = {}): string {
  const lines: string[] = [
    `User Requirements: ${JSON.stringify(ctx.userRequirements ?? [])}`,
    `Deliverables: ${JSON.stringify(ctx.deliverables ?? [])}`,
    `Revised Or Superseded Direction: ${JSON.stringify(ctx.revisedOrSupersededDirection ?? [])}`,
    `User Decisions: ${JSON.stringify(ctx.userDecisions ?? [])}`,
    `Questions And Information Gaps: ${JSON.stringify(ctx.questionsAndInformationGaps ?? [])}`,
    `Control Boundaries: ${JSON.stringify(ctx.controlBoundaries ?? [])}`,
    `Observed Work: ${JSON.stringify(ctx.observedWork ?? [])}`,
    `Observed Critical Facts: ${JSON.stringify(ctx.observedCriticalFacts ?? [])}`,
    `Relevant Learnings: ${JSON.stringify(ctx.relevantLearnings ?? [])}`,
    `Deliberation Needed: ${ctx.deliberationNeeded ?? true}`,
  ];
  if (ctx.deliberationReason !== undefined) {
    lines.push(`Deliberation Reason: ${ctx.deliberationReason}`);
  }
  lines.push(`Active Human Input Source Ids: ${JSON.stringify(ctx.activeHumanInputSourceIds ?? [])}`);
  lines.push(`Superseded Human Input Source Ids: ${JSON.stringify(ctx.supersededHumanInputSourceIds ?? [])}`);
  return lines.join("\n");
}
