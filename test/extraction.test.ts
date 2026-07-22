// Tests for context vector extraction pass.

import { describe, expect, it } from "vitest";
import { extractContextFromMessages, EXTRACTION_SYSTEM_PROMPT, getDefaultExtractedContext } from "../src/extraction.js";
import type { ModelCallFn } from "../src/core.js";
import type { AgentMessage } from "@earendil-works/pi-agent-core";

describe("src/extraction.ts", () => {
  it("provides default safe extracted context on failure or empty input", () => {
    const defaultCtx = getDefaultExtractedContext();
    expect(defaultCtx.clarityAndAmbiguityScore).toBe("CLEAR");
    expect(defaultCtx.userIntentAndMotive).toBeDefined();
    expect(defaultCtx.activeConstraintsAndGuards).toBeDefined();
  });

  it("extracts 5 context vectors from valid LLM JSON response", async () => {
    const mockJson = JSON.stringify({
      userIntentAndMotive: "Implement reality-grounded deliberation.",
      activeConstraintsAndGuards: "read-only mode active",
      verifiedFactsInventory: "src/types.ts updated",
      evidenceFreshnessDelta: "Code changed 2 min ago, tests not run yet",
      clarityAndAmbiguityScore: "AMBIGUOUS",
      missingDetails: "Clarify model provider for extraction pass",
    });

    const mockCallFn: ModelCallFn = async (key, system, _user) => {
      expect(key).toBe("extraction");
      expect(system).toBe(EXTRACTION_SYSTEM_PROMPT);
      return mockJson;
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Implement reality-grounded deliberation.", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, mockCallFn);

    expect(ctx.userIntentAndMotive).toBe("Implement reality-grounded deliberation.");
    expect(ctx.activeConstraintsAndGuards).toBe("read-only mode active");
    expect(ctx.verifiedFactsInventory).toBe("src/types.ts updated");
    expect(ctx.evidenceFreshnessDelta).toBe("Code changed 2 min ago, tests not run yet");
    expect(ctx.clarityAndAmbiguityScore).toBe("AMBIGUOUS");
    expect(ctx.missingDetails).toBe("Clarify model provider for extraction pass");
  });

  it("falls back to default context gracefully when extraction model fails", async () => {
    const failingCallFn: ModelCallFn = async () => {
      throw new Error("API rate limit exceeded");
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Hello", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, failingCallFn);

    expect(ctx.userIntentAndMotive).toBe("Hello");
    expect(ctx.clarityAndAmbiguityScore).toBe("CLEAR");
  });

  it("falls back gracefully when extraction returns invalid JSON", async () => {
    const invalidCallFn: ModelCallFn = async () => {
      return "I cannot parse this context into JSON format.";
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Build a feature", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, invalidCallFn);

    expect(ctx.userIntentAndMotive).toContain("Build a feature");
    expect(ctx.clarityAndAmbiguityScore).toBe("CLEAR");
  });
});
