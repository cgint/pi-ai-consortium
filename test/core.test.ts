// Tests for ConsortiumCore — pure logic, no Pi dependency.

import { describe, expect, it } from "vitest";
import { ConsortiumCore, type ModelCallFn } from "../src/core.js";
import type { ConsortiumConfig } from "../src/types.js";

/** Mock model call function that returns predetermined responses. */
function createMockCallFn(responses: Record<string, string>): ModelCallFn {
  return async (modelKey, _system, _user, _maxTokens, _temperature, _signal) => {
    return responses[modelKey] ?? `[mock ${modelKey}]`;
  };
}

const baseConfig: ConsortiumConfig = {
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
};

describe("ConsortiumCore", () => {
  it("skips probe execution when governor decides deliberation is not needed", async () => {
    let probeExecuted = false;
    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") {
        return JSON.stringify({
          userIntentAndMotive: "Test",
          activeConstraintsAndGuards: "None",
          verifiedFactsInventory: "Facts",
          evidenceFreshnessDelta: "Fresh",
          clarityAndAmbiguityScore: "CLEAR",
          deliberationNeeded: false,
          deliberationReason: "Routine status query",
        });
      }
      probeExecuted = true;
      return "WARN Probe output";
    };

    const core = new ConsortiumCore({ ...baseConfig, governorMode: "smart_extractor" }, callFn);
    const messages = [{ role: "user" as const, content: "What is the current status?", timestamp: Date.now() }];
    const result = await core.deliberate(messages);

    expect(result.skippedByGovernor).toBe(true);
    expect(result.governorReason).toBe("Routine status query");
    expect(result.probes).toHaveLength(0);
    expect(probeExecuted).toBe(false);
  });

  it("runs full deliberation cycle (diverge → converge)", async () => {
    const callFn = createMockCallFn({
      "probe:0": "WARN Hidden assumptions about auth strategy.",
      "probe:1": "WARN This could break under load.",
      synthesis: "Synthesized: Watch for hidden assumptions AND load issues.",
    });
    const core = new ConsortiumCore(baseConfig, callFn);
    const result = await core.deliberate("Build me a REST API");

    expect(result.synthesis).toBe("Synthesized: Watch for hidden assumptions AND load issues.");
    expect(result.probes).toHaveLength(2);
    expect(result.probes[0].role).toBe("clarifier");
    expect(result.probes[1].role).toBe("contrarian");
    expect(result.errors).toBeUndefined();
  });

  it("collects per-probe errors without failing entirely", async () => {
    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "probe:0") {
        throw new Error("Network timeout");
      }
      return modelKey === "probe:1" ? "WARN Probe 1 OK" : "Synthesis OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);
    const result = await core.deliberate("Test input");

    expect(result.probes[0].text).toContain("[error: Network timeout]");
    expect(result.probes[1].text).toBe("WARN Probe 1 OK");
    expect(result.synthesis).toBe("Synthesis OK");
    expect(result.errors).toBeDefined();
    expect(result.errors![0]).toContain("Probe \"clarifier\"");
  });

  it("handles synthesis failure gracefully", async () => {
    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey.startsWith("probe:")) {
        return "WARN Probe OK";
      }
      throw new Error("Synthesis model down");
    };
    const core = new ConsortiumCore(baseConfig, callFn);
    const result = await core.deliberate("Test input");

    expect(result.synthesis).toContain("[Synthesis failed:");
    expect(result.errors).toBeDefined();
    expect(result.errors!.some((e) => e.startsWith("Synthesis:"))).toBe(true);
  });

  it("respects per-probe timeout", async () => {
    const callFn: ModelCallFn = async (_modelKey, _system, _user, _mt, _temp, signal) => {
      // Sleep 2s, but abort immediately if signal fires
      await new Promise<void>((_, reject) => {
        const sleepTimer = setTimeout(() => reject(new Error("Slow")), 2000);
        signal?.addEventListener(
          "abort",
          () => {
            clearTimeout(sleepTimer);
            reject(new Error("Aborted"));
          },
          { once: true },
        );
      });
      return "WARN Slow response";
    };
    const config: ConsortiumConfig = {
      ...baseConfig,
      probeTimeoutMs: 100, // Short timeout
    };
    const core = new ConsortiumCore(config, callFn);
    const result = await core.deliberate("Test input");

    expect(result.probes.every((p) => p.text.includes("[error:"))).toBe(true);
    expect(result.errors).toBeDefined();
  });

  it("passes correct modelKey to callModel", async () => {
    const keys: string[] = [];
    const callFn: ModelCallFn = async (modelKey) => {
      keys.push(modelKey);
      return "WARN OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);
    await core.deliberate("Test");

    expect(keys).toEqual(["probe:0", "probe:1", "synthesis"]);
  });

  it("aborts deliberation when external signal is fired", async () => {
    const controller = new AbortController();
    const callFn: ModelCallFn = async (_modelKey, _system, _user, _mt, _temp, signal) => {
      // Slow enough that external abort fires during probe phase
      await new Promise((resolve) => setTimeout(resolve, 500));
      if (signal?.aborted) throw new Error("Aborted");
      return "WARN OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);

    // Abort after 50ms — probes are still running
    setTimeout(() => controller.abort(), 50);

    const result = await core.deliberate("Test input", controller.signal);

    // Should degrade gracefully — probes aborted, synthesis attempted
    expect(result.errors).toBeDefined();
    expect(result.errors!.some((e) => e.includes("Aborted") || e.includes("Synthesis"))).toBe(true);
  });

  it("aborts immediately when signal is already aborted", async () => {
    const controller = new AbortController();
    controller.abort(); // Pre-abort

    let callCount = 0;
    const callFn: ModelCallFn = async () => {
      callCount++;
      return "WARN OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);

    await expect(core.deliberate("Test input", controller.signal)).rejects.toThrow("Deliberation aborted");
    expect(callCount).toBe(0); // No model calls should have been made
  });

  it("rejects probe output that doesn't start with severity tag or NO_CONTRIBUTION", async () => {
    const callFn = createMockCallFn({
      "probe:0": "Today is Monday, June 29, 2026.",
      "probe:1": "WARN This could break under load.",
      synthesis: "Synthesized: Load warning noted.",
    });
    const core = new ConsortiumCore(baseConfig, callFn);
    const result = await core.deliberate("What is the day today?");

    // probe:0 was coerced to NO_CONTRIBUTION, probe:1 passed through
    expect(result.probes[0].text).toBe("NO_CONTRIBUTION");
    expect(result.probes[1].text).toBe("WARN This could break under load.");
    expect(result.synthesis).toBe("Synthesized: Load warning noted.");
  });

  it("executes probes serially when executionMode is serial", async () => {
    const order: string[] = [];
    const callFn: ModelCallFn = async (modelKey) => {
      order.push(`${modelKey}-start`);
      await new Promise((r) => setTimeout(r, 50));
      order.push(`${modelKey}-end`);
      return "WARN OK";
    };
    const core = new ConsortiumCore({ ...baseConfig, executionMode: "serial" }, callFn);
    await core.deliberate("Test");

    // Serial: probe:0 completes before probe:1 starts
    expect(order).toEqual([
      "probe:0-start",
      "probe:0-end",
      "probe:1-start",
      "probe:1-end",
      "synthesis-start",
      "synthesis-end",
    ]);
  });

  it("executes probes in parallel when executionMode is parallel", async () => {
    const order: string[] = [];
    const callFn: ModelCallFn = async (modelKey) => {
      order.push(`${modelKey}-start`);
      await new Promise((r) => setTimeout(r, 50));
      order.push(`${modelKey}-end`);
      return "WARN OK";
    };
    const core = new ConsortiumCore({ ...baseConfig, executionMode: "parallel" }, callFn);
    await core.deliberate("Test");

    // Parallel: both probes start before either ends
    expect(order[0]).toBe("probe:0-start");
    expect(order[1]).toBe("probe:1-start");
    // Both ends come after both starts
    expect(order.findIndex((o) => o === "probe:0-end")).toBeGreaterThan(1);
    expect(order.findIndex((o) => o === "probe:1-end")).toBeGreaterThan(1);
  });

  it("defaults to serial when executionMode is undefined", async () => {
    const order: string[] = [];
    const callFn: ModelCallFn = async (modelKey) => {
      order.push(`${modelKey}-start`);
      await new Promise((r) => setTimeout(r, 30));
      order.push(`${modelKey}-end`);
      return "WARN OK";
    };
    const config = { ...baseConfig };
    delete (config as any).executionMode;
    const core = new ConsortiumCore(config, callFn);
    await core.deliberate("Test");

    // Should behave serially (probe:0 completes before probe:1 starts)
    expect(order[0]).toBe("probe:0-start");
    expect(order[1]).toBe("probe:0-end");
    expect(order[2]).toBe("probe:1-start");
    expect(order[3]).toBe("probe:1-end");
  });

  it("appends roleLens to user context per probe", async () => {
    const receivedUsers: string[] = [];
    const callFn: ModelCallFn = async (_modelKey, _system, user) => {
      receivedUsers.push(user);
      return "WARN OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);
    await core.deliberate("Test context");

    // Each probe gets userContext + separator + its own roleLens
    expect(receivedUsers[0]).toContain("Test context");
    expect(receivedUsers[0]).toContain("## Lens: clarify");
    expect(receivedUsers[1]).toContain("Test context");
    expect(receivedUsers[1]).toContain("## Lens: challenge");
    // Role lens appears at the tail, after the shared context
    expect(receivedUsers[0]).toMatch(/Test context[\s\-]+## Lens: clarify/);
  });

  it("works without roleLens (backward compat)", async () => {
    const callFn = createMockCallFn({
      "probe:0": "WARN OK",
      "probe:1": "WARN OK",
      synthesis: "Synthesized.",
    });
    const config: ConsortiumConfig = {
      ...baseConfig,
      probes: baseConfig.probes.map((p) => ({ ...p, roleLens: "" })),
    };
    const core = new ConsortiumCore(config, callFn);
    const result = await core.deliberate("Test");
    expect(result.synthesis).toBe("Synthesized.");
  });

  it("runs extraction pass and passes XML payload to probes when messages array is provided", async () => {
    const receivedUsers: Record<string, string> = {};
    const mockExtractionJson = JSON.stringify({
      userIntentAndMotive: "Test extraction integration",
      activeConstraintsAndGuards: "read-only",
      verifiedFactsInventory: "facts clean",
      evidenceFreshnessDelta: "no delta",
      clarityAndAmbiguityScore: "CLEAR",
    });

    const callFn: ModelCallFn = async (modelKey, _system, user) => {
      receivedUsers[modelKey] = user;
      if (modelKey === "extraction") {
        return mockExtractionJson;
      }
      return "WARN Reality check passed.";
    };

    const core = new ConsortiumCore(baseConfig, callFn);
    const messages = [
      { role: "user" as const, content: "Test extraction integration", timestamp: Date.now() },
    ];

    const result = await core.deliberate(messages);

    expect(receivedUsers["extraction"]).toBeDefined();
    expect(receivedUsers["probe:0"]).toContain("<probe_input_payload>");
    expect(receivedUsers["probe:0"]).toContain("<user_intent_motive>Test extraction integration</user_intent_motive>");
    expect(result.extractedContext).toBeDefined();
    expect(result.extractedContext?.userIntentAndMotive).toBe("Test extraction integration");
  });
});