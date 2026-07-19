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
    { role: "clarifier", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Clarify" },
    { role: "contrarian", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Challenge" },
  ],
  synthesis: { provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Synthesize" },
  maxProbeTokens: 256,
  maxSynthesisTokens: 256,
  probeTemperature: 0.7,
  synthesisTemperature: 0.3,
  probeTimeoutMs: 5000,
  totalTimeoutMs: 10000,
};

describe("ConsortiumCore", () => {
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
      // Simulate slow response
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (signal?.aborted) throw new Error("Aborted");
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
});