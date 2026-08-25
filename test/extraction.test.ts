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
      activeHumanInputSourceIds: ["human-4"],
      supersededHumanInputSourceIds: ["human-1"],
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Add a new requirement.", timestamp: Date.now() },
    ];

    const ctx = await extractContextFromMessages(messages, mockCallFn, previousContext);

    expect(receivedUserPrompt).toContain("<previous_extracted_context_baseline>");
    expect(receivedUserPrompt).toContain("Accumulated requirement");
    const baseline = receivedUserPrompt.slice(
      receivedUserPrompt.indexOf("<previous_extracted_context_baseline>"),
      receivedUserPrompt.indexOf("</previous_extracted_context_baseline>"),
    );
    expect(baseline).not.toContain("activeHumanInputSourceIds");
    expect(baseline).not.toContain("supersededHumanInputSourceIds");
    expect(ctx.userRequirements).toContain("Accumulated requirement");
    expect(ctx.userRequirements).toContain("New requirement");
  });

  it("passes complete conversation history (>10 messages) to LLM without truncation", async () => {
    let receivedUserPrompt = "";
    const mockCallFn: ModelCallFn = async (_key, _system, user) => {
      receivedUserPrompt = user;
      return JSON.stringify({
        userRequirements: ["Earliest Turn 1 Goal", "Latest Turn 15 Goal"],
        deliverables: [],
        revisedOrSupersededDirection: [],
        userDecisions: [],
        questionsAndInformationGaps: [],
        controlBoundaries: [],
        observedWork: [],
        observedCriticalFacts: [],
        relevantLearnings: [],
        deliberationNeeded: true,
      });
    };

    const messages: AgentMessage[] = Array.from({ length: 15 }, (_, i) => ({
      role: i % 2 === 0 ? "user" : "assistant",
      content: `Message ${i + 1}: Turn detail for item ${i + 1}`,
      timestamp: Date.now() + i * 1000,
    }));

    await extractContextFromMessages(messages, mockCallFn);

    expect(receivedUserPrompt).toContain("Message 1: Turn detail for item 1");
    expect(receivedUserPrompt).toContain("Message 15: Turn detail for item 15");
  });

  it("ends C1 input with original and current genuine-human focus", async () => {
    let receivedUserPrompt = "";
    const mockCallFn: ModelCallFn = async (_key, _system, user) => {
      receivedUserPrompt = user;
      return JSON.stringify({
        userRequirements: ["Original mandate", "Current direction"],
        deliverables: [], revisedOrSupersededDirection: [], userDecisions: [],
        questionsAndInformationGaps: [], controlBoundaries: [], observedWork: [], observedCriticalFacts: [], relevantLearnings: [],
        deliberationNeeded: false,
      });
    };
    const previousContext = getDefaultExtractedContext();
    await extractContextFromMessages([
      { role: "user", content: "Original mandate", timestamp: Date.now() },
      { role: "user", content: "[CONSORTIUM DELIBERATION] synthetic note", timestamp: Date.now() },
      { role: "assistant", content: "Work in progress", timestamp: Date.now() },
      { role: "user", content: "Current direction", timestamp: Date.now() },
    ], mockCallFn, previousContext);

    const focus = receivedUserPrompt.slice(receivedUserPrompt.lastIndexOf("<human_input_focus>"));
    expect(receivedUserPrompt.lastIndexOf("<human_input_focus>")).toBeGreaterThan(receivedUserPrompt.lastIndexOf("<previous_extracted_context_baseline>"));
    expect(focus).toContain("Original mandate");
    expect(focus).toContain("Current direction");
    expect(focus).not.toContain("synthetic note");
    expect(receivedUserPrompt.trim().endsWith("</human_input_focus>")).toBe(true);
  });

  it("propagates errors on LLM call failure (no silent fallback)", async () => {
    const failingCallFn: ModelCallFn = async () => {
      throw new Error("API network failure");
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Build a feature", timestamp: Date.now() },
    ];

    await expect(extractContextFromMessages(messages, failingCallFn))
      .rejects.toThrow("API network failure");
  });

  it("propagates errors on invalid JSON from model", async () => {
    const badJsonCallFn: ModelCallFn = async () => {
      return "not valid json {{{";
    };

    const messages: AgentMessage[] = [
      { role: "user", content: "Build a feature", timestamp: Date.now() },
    ];

    await expect(extractContextFromMessages(messages, badJsonCallFn))
      .rejects.toThrow("JSON");
  });
});
