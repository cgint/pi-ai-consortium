// Tests for formatVisibleMessage — panel formatting for deliberation results.

import { describe, expect, it } from "vitest";
import { formatVisibleMessage } from "../src/ui.js";
import type { DeliberationResult } from "../src/types.js";

function makeResult(overrides: Partial<DeliberationResult>): DeliberationResult {
  return {
    probes: [],
    synthesis: "NO_CONTRIBUTION",
    ...overrides,
  };
}

describe("formatVisibleMessage", () => {
  it("shows extraction failure with probes skipped", () => {
    const result = makeResult({
      probes: [],
      synthesis: "NO_CONTRIBUTION",
      errors: ["Extraction: Empty response from google/gemini-3.7-flash (stopReason=error, totalTokens=0)"],
    });
    const output = formatVisibleMessage(result);
    expect(output).toContain("⚠ Consortium deliberation — extraction failed, probes skipped");
    expect(output).toContain("Empty response from google/gemini-3.7-flash");
    expect(output).not.toContain("0/0 probes contributed");
  });

  it("shows all probes FAILED when all probes errored", () => {
    const result = makeResult({
      probes: [
        { role: "architect", text: "[error: provider rejected]" },
        { role: "clarifier", text: "[error: provider rejected]" },
        { role: "contrarian", text: "[error: provider rejected]" },
        { role: "navigator", text: "[error: provider rejected]" },
        { role: "responder", text: "[error: provider rejected]" },
      ],
      synthesis: "NO_CONTRIBUTION",
      extractedContext: {
        userRequirements: ["test"], deliverables: [], revisedOrSupersededDirection: [],
        userDecisions: [], questionsAndInformationGaps: [], controlBoundaries: [],
        observedWork: [], observedCriticalFacts: [], relevantLearnings: [],
      },
      errors: [
        'Probe "architect": provider rejected',
        'Probe "clarifier": provider rejected',
        'Probe "contrarian": provider rejected',
        'Probe "navigator": provider rejected',
        'Probe "responder": provider rejected',
      ],
    });
    const output = formatVisibleMessage(result);
    expect(output).toContain("⚠ Consortium deliberation — 5/5 probes FAILED");
    expect(output).toContain("architect: ERROR — provider rejected");
    expect(output).not.toContain("architect: NO_CONTRIBUTION");
  });

  it("shows mixed probes: some failed, some no-contribution", () => {
    const result = makeResult({
      probes: [
        { role: "architect", text: "[error: transient failure]" },
        { role: "clarifier", text: "NO_CONTRIBUTION" },
        { role: "contrarian", text: "WARN something to flag" },
      ],
      synthesis: "Synthesized result",
      extractedContext: {
        userRequirements: ["test"], deliverables: [], revisedOrSupersededDirection: [],
        userDecisions: [], questionsAndInformationGaps: [], controlBoundaries: [],
        observedWork: [], observedCriticalFacts: [], relevantLearnings: [],
      },
      errors: ['Probe "architect": transient failure'],
    });
    const output = formatVisibleMessage(result);
    expect(output).toContain("1/3 probes contributed");
    expect(output).toContain("(1 failed)");
    expect(output).toContain("architect: ERROR — transient failure");
    expect(output).toContain("clarifier: NO_CONTRIBUTION");
  });

  it("shows healthy all-NO_CONTRIBUTION without error markers", () => {
    const result = makeResult({
      probes: [
        { role: "architect", text: "NO_CONTRIBUTION" },
        { role: "clarifier", text: "NO_CONTRIBUTION" },
      ],
      synthesis: "NO_CONTRIBUTION",
      extractedContext: {
        userRequirements: ["test"], deliverables: [], revisedOrSupersededDirection: [],
        userDecisions: [], questionsAndInformationGaps: [], controlBoundaries: [],
        observedWork: [], observedCriticalFacts: [], relevantLearnings: [],
      },
    });
    const output = formatVisibleMessage(result);
    expect(output).toContain("0/2 probes contributed (nothing to add)");
    expect(output).not.toContain("ERROR");
    expect(output).not.toContain("⚠");
  });

  it("shows healthy all-NO_CONTRIBUTION with extraction error in status but no probe errors", () => {
    // Extraction error is in errors[] but probes ran and all returned NO_CONTRIBUTION.
    // This is an edge case: extraction succeeded (didn't throw), but an error
    // was logged for another reason. The probe display should not show FAILED.
    const result = makeResult({
      probes: [
        { role: "architect", text: "NO_CONTRIBUTION" },
        { role: "clarifier", text: "NO_CONTRIBUTION" },
      ],
      synthesis: "NO_CONTRIBUTION",
      errors: ["Something else went wrong"],
    });
    const output = formatVisibleMessage(result);
    // "Something else went wrong" is not an Extraction: error, so it shouldn't
    // trigger the "extraction failed" header.
    expect(output).toContain("0/2 probes contributed (nothing to add)");
    expect(output).not.toContain("extraction failed");
  });

  it("shows governor skip", () => {
    const result = makeResult({
      skippedByGovernor: true,
      governorReason: "Max turn gap (3) not reached (1/3)",
    });
    const output = formatVisibleMessage(result);
    expect(output).toContain("skipped (Max turn gap (3) not reached (1/3))");
  });
});
