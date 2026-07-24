// Tests for high-level 9-slot strategic context vector extraction.

import { describe, expect, it } from "vitest";
import {
  extractContextFromMessages,
  EXTRACTION_SYSTEM_PROMPT,
  getDefaultExtractedContext,
} from "../src/extraction.js";
import type { ModelCallFn } from "../src/core.js";
import type { AgentMessage } from "@earendil-works/pi-agent-core";

describe("src/extraction.ts — 9-slot strategic context", () => {
  it("provides default safe extracted context with 9 slots on empty or invalid input", () => {
    const defaultCtx = getDefaultExtractedContext();
    expect(defaultCtx.userRequirements).toBeDefined();
    expect(Array.isArray(defaultCtx.userRequirements)).toBe(true);
    expect(Array.isArray(defaultCtx.deliverables)).toBe(true);
    expect(Array.isArray(defaultCtx.revisedOrSupersededDirection)).toBe(true);
    expect(Array.isArray(defaultCtx.userDecisions)).toBe(true);
    expect(Array.isArray(defaultCtx.questionsAndInformationGaps)).toBe(true);
    expect(Array.isArray(defaultCtx.controlBoundaries)).toBe(true);
    expect(Array.isArray(defaultCtx.observedWork)).toBe(true);
    expect(Array.isArray(defaultCtx.observedCriticalFacts)).toBe(true);
    expect(Array.isArray(defaultCtx.relevantLearnings)).toBe(true);
    expect(defaultCtx.deliberationNeeded).toBe(true);
  });

  it("extracts 9 strategic context vector arrays from valid LLM JSON response", async () => {
    const mockJson = JSON.stringify({
      userRequirements: ["Implement 9-slot strategic extraction", "Preserve KV-cache prefix"],
      deliverables: ["Updated src/types.ts", "Updated TUI notifications in src/ui.ts"],
      revisedOrSupersededDirection: ["Filter out edit tool line-mismatch errors"],
      userDecisions: ["Use 9 explicit strategic slots"],
      questionsAndInformationGaps: ["None — requirements are clear"],
      controlBoundaries: ["Allowed paths: dev-external/pi-ai-consortium and concept repo"],
      observedWork: ["Updated adaptation plan v4 in concept repository"],
      observedCriticalFacts: ["Pass 1 Pass 2 Pass 3 serial pipeline active"],
      relevantLearnings: ["Operational friction pollutes probe context"],
      deliberationNeeded: true,
      deliberationReason: "Unverified TUI implementation code edits",
    });

    const mockCallFn: ModelCallFn = async (key, system, _user) => {
      expect(key).toBe("extraction");
      expect(system).toBe(EXTRACTION_SYSTEM_PROMPT);
      return mockJson;
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Implement 9-slot strategic context extraction.", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, mockCallFn);

    expect(ctx.userRequirements).toEqual(["Implement 9-slot strategic extraction", "Preserve KV-cache prefix"]);
    expect(ctx.deliverables).toEqual(["Updated src/types.ts", "Updated TUI notifications in src/ui.ts"]);
    expect(ctx.revisedOrSupersededDirection).toEqual(["Filter out edit tool line-mismatch errors"]);
    expect(ctx.userDecisions).toEqual(["Use 9 explicit strategic slots"]);
    expect(ctx.questionsAndInformationGaps).toEqual(["None — requirements are clear"]);
    expect(ctx.controlBoundaries).toEqual(["Allowed paths: dev-external/pi-ai-consortium and concept repo"]);
    expect(ctx.observedWork).toEqual(["Updated adaptation plan v4 in concept repository"]);
    expect(ctx.observedCriticalFacts).toEqual(["Pass 1 Pass 2 Pass 3 serial pipeline active"]);
    expect(ctx.relevantLearnings).toEqual(["Operational friction pollutes probe context"]);
    expect(ctx.deliberationNeeded).toBe(true);
  });

  it("includes ACCUMULATION RULE in EXTRACTION_SYSTEM_PROMPT", () => {
    expect(EXTRACTION_SYSTEM_PROMPT).toContain("ACCUMULATION RULE:");
    expect(EXTRACTION_SYSTEM_PROMPT).toContain("PRESERVE and ACCUMULATE durable user intent");
  });

  it("passes Previous Extracted Context Baseline to LLM when previousContext is provided", async () => {
    let receivedUserPrompt = "";
    const mockCallFn: ModelCallFn = async (_key, _system, user) => {
      receivedUserPrompt = user;
      return JSON.stringify({
        userRequirements: ["Accumulated requirement", "New requirement"],
        deliverables: ["Deliverable 1"],
        revisedOrSupersededDirection: [],
        userDecisions: [],
        questionsAndInformationGaps: [],
        controlBoundaries: ["Control 1"],
        observedWork: ["Work step 2"],
        observedCriticalFacts: ["Fact 2"],
        relevantLearnings: [],
        deliberationNeeded: true,
      });
    };

    const previousContext: ExtractedContext = {
      userRequirements: ["Accumulated requirement"],
      deliverables: [],
      revisedOrSupersededDirection: [],
      userDecisions: [],
      questionsAndInformationGaps: [],
      controlBoundaries: ["Control 1"],
      observedWork: ["Work step 1"],
      observedCriticalFacts: ["Fact 1"],
      relevantLearnings: [],
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Add a new requirement.", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, mockCallFn, previousContext);

    expect(receivedUserPrompt).toContain("Previous Extracted Context Baseline:");
    expect(receivedUserPrompt).toContain("Accumulated requirement");
    expect(ctx.userRequirements).toContain("Accumulated requirement");
    expect(ctx.userRequirements).toContain("New requirement");
  });

  it("falls back gracefully to default 9-slot context on LLM call failure", async () => {
    const failingCallFn: ModelCallFn = async () => {
      throw new Error("API network failure");
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Build a feature", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, failingCallFn);

    expect(ctx.userRequirements[0]).toContain("Build a feature");
    expect(ctx.deliverables).toEqual([]);
    expect(ctx.deliberationNeeded).toBe(true);
  });
});
