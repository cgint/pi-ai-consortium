/**
 * Pins the Ax wire-key vs display-name label contract for the extraction program.
 *
 * Background (2026-08-25 spike + source audit, @ax-llm/ax@24.0.8):
 *   - The rendered DSPy prompt's <formatting_rules> block says:
 *       "using each exact wire key shown in <output_fields> as the field name"
 *   - But the extraction parser (streamingText.ts) matches on `field.title`
 *     (the Title-Case display name), NOT the camelCase wire key.
 *   - The spike empirically confirmed: wire-key labels → "Required field not
 *     found"; display-name labels → parsed on first attempt.
 *
 * This test drives the *production* extraction path (extractContextFromMessages
 * + AxPiService + the module-level extractionProgram) and asserts:
 *   1. The rendered system prompt contains the display-name labels the parser
 *      requires (e.g. "User Requirements").
 *   2. A response using display-name labels parses on the first call.
 *   3. A response using camelCase wire keys triggers a correction retry (≥2
 *      ModelCallFn calls) and either recovers or throws — we pin whichever
 *      the installed Ax version actually does.
 *
 * No real LLM is involved; the ModelCallFn is a mock that captures prompts and
 * returns canned labeled-field strings.
 */
import { describe, expect, it } from "vitest";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { ConsortiumCore, type ModelCallFn } from "../src/core.js";
import type { ConsortiumConfig } from "../src/types.js";
import { extractContextFromMessages } from "../src/extraction.js";
import { extractionLabeled } from "./extraction-mock.js";

const MESSAGES: AgentMessage[] = [
  { role: "user", content: "Please implement feature X with a parity test.", timestamp: 1_000 },
  { role: "assistant", content: "Working on it.", timestamp: 2_000 },
];

/**
 * Build a wire-key-labeled response (camelCase labels, JSON arrays).
 * This is what the prompt's <formatting_rules> literally instructs.
 */
function wireKeyLabeled(userRequirements: string[], controlBoundaries: string[] = ["read-only"]): string {
  return [
    `userRequirements: ${JSON.stringify(userRequirements)}`,
    `deliverables: []`,
    `revisedOrSupersededDirection: []`,
    `userDecisions: []`,
    `questionsAndInformationGaps: []`,
    `controlBoundaries: ${JSON.stringify(controlBoundaries)}`,
    `observedWork: []`,
    `observedCriticalFacts: []`,
    `relevantLearnings: []`,
    `deliberationNeeded: false`,
    `deliberationReason: "Routine"`,
  ].join("\n");
}

describe("Ax extraction label contract (wire key vs display name)", () => {
  it("rendered prompt contains the display-name labels the parser matches", async () => {
    let capturedSystem = "";
    const mockCallFn: ModelCallFn = async (_key, system) => {
      capturedSystem = system;
      return extractionLabeled({
        userRequirements: ["Captured"],
        deliberationNeeded: false,
        deliberationReason: "test",
      });
    };

    await extractContextFromMessages(MESSAGES, mockCallFn);

    // The parser matches these exact Title-Case labels. The prompt must
    // present them so a real LLM can produce parseable output.
    for (const label of [
      "User Requirements",
      "Deliverables",
      "Control Boundaries",
      "Observed Work",
      "Deliberation Needed",
    ]) {
      expect(capturedSystem, `prompt should contain display label "${label}"`).toContain(label);
    }
  });

  it("parses a display-name-labeled response on the first call", async () => {
    let callCount = 0;
    const mockCallFn: ModelCallFn = async () => {
      callCount++;
      return extractionLabeled({
        userRequirements: ["Display name works"],
        controlBoundaries: ["read-only"],
        observedWork: ["parsed first try"],
        deliberationNeeded: false,
        deliberationReason: "clean parse",
      });
    };

    const ctx = await extractContextFromMessages(MESSAGES, mockCallFn);

    expect(callCount).toBe(1);
    expect(ctx.userRequirements).toEqual(["Display name works"]);
    expect(ctx.controlBoundaries).toEqual(["read-only"]);
  });

  it("documents the wire-key-labeled response contract (correction retry or throw)", async () => {
    let callCount = 0;
    let lastPrompt = "";
    const mockCallFn: ModelCallFn = async (_key, _system, user) => {
      callCount++;
      lastPrompt = user;
      // First attempt: model follows the <formatting_rules> "wire key"
      // instruction and emits camelCase labels.
      if (callCount === 1) {
        return wireKeyLabeled(["Wire key attempt"]);
      }
      // Correction attempt (if Ax retries): return a display-name response.
      return extractionLabeled({
        userRequirements: ["Recovered after correction"],
        controlBoundaries: ["read-only"],
        deliberationNeeded: false,
        deliberationReason: "recovered",
      });
    };

    let recovered = false;
    let threw = false;
    try {
      const ctx = await extractContextFromMessages(MESSAGES, mockCallFn);
      recovered = true;
      // If it recovered, the values must come from the second (display-name) response.
      expect(ctx.userRequirements).toEqual(["Recovered after correction"]);
    } catch {
      threw = true;
    }

    // Pin the observed contract: EITHER Ax recovers via a correction retry
    // (≥2 calls), OR it throws after exhausting retries. Both are valid
    // behaviors to document; what we must NOT see is a silent no-op parse
    // (0 or 1 call with empty/garbage values).
    if (recovered) {
      expect(callCount, "recovery implies a correction retry occurred").toBeGreaterThanOrEqual(2);
      // The correction prompt should steer the model toward display names.
      expect(lastPrompt).toMatch(/User Requirements|display/i);
    } else {
      expect(threw).toBe(true);
      expect(callCount, "throw path should still attempt a retry before giving up").toBeGreaterThanOrEqual(2);
    }
    // Invariant: a wire-key-only response must never silently produce an
    // empty extraction on a single call.
    expect(callCount).toBeGreaterThanOrEqual(1);
  });
});

describe("Ax extraction transport parity (adapter → ModelCallFn)", () => {
  const PIPELINE_CONFIG: ConsortiumConfig = {
    probes: [
      { role: "clarifier", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Clarify", roleLens: "## Lens: clarify" },
      { role: "contrarian", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Challenge", roleLens: "## Lens: challenge" },
    ],
    synthesis: { provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Synthesize" },
    maxProbeTokens: 256,
    maxSynthesisTokens: 256,
    probeTemperature: 0.7,
    synthesisTemperature: 0.3,
    probeTimeoutMs: 5000,
    totalTimeoutMs: 10000,
    executionMode: "serial",
    governorMode: "smart_extractor",
  };

  it("passes the caller's AbortSignal through to the transport", async () => {
    const controller = new AbortController();
    let receivedSignal: AbortSignal | undefined;
    const mockCallFn: ModelCallFn = async (_key, _system, _user, _max, _temp, sig) => {
      receivedSignal = sig;
      return extractionLabeled({ userRequirements: ["ok"], deliberationNeeded: false });
    };

    await extractContextFromMessages(MESSAGES, mockCallFn, undefined, controller.signal);

    expect(receivedSignal, "a signal must reach ModelCallFn").toBeDefined();
    // Ax wraps the signal in an AbortSignal.any() composite; propagation
    // (not identity) is the contract that matters for cancellation.
    controller.abort();
    expect(receivedSignal!.aborted, "aborting the caller's signal must abort the transport signal").toBe(true);
  });

  it("passes maxTokens=1024 and temperature=0.2 through to the transport", async () => {
    let receivedMax: number | undefined;
    let receivedTemp: number | undefined;
    const mockCallFn: ModelCallFn = async (_key, _system, _user, max, temp) => {
      receivedMax = max;
      receivedTemp = temp;
      return extractionLabeled({ userRequirements: ["ok"], deliberationNeeded: false });
    };

    await extractContextFromMessages(MESSAGES, mockCallFn);

    expect(receivedMax).toBe(1024);
    expect(receivedTemp).toBe(0.2);
  });

  it("makes exactly one extraction call through the full deliberate() pipeline", async () => {
    const callKeys: string[] = [];
    const mockCallFn: ModelCallFn = async (modelKey) => {
      callKeys.push(modelKey);
      if (modelKey === "extraction") {
        return extractionLabeled({
          userRequirements: ["one call"],
          controlBoundaries: ["read-only"],
          observedWork: ["done"],
          deliberationNeeded: false,
          deliberationReason: "no gap",
        });
      }
      return "NO_CONTRIBUTION";
    };

    const core = new ConsortiumCore(PIPELINE_CONFIG, mockCallFn);
    await core.deliberate(MESSAGES);

    expect(callKeys.filter((k) => k === "extraction")).toHaveLength(1);
  });
});
