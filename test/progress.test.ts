// Tests for progress callback in ConsortiumCore.

import { describe, expect, it, vi } from "vitest";
import { ConsortiumCore, type ModelCallFn } from "../src/core.js";
import type { ConsortiumConfig } from "../src/types.js";

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

describe("ConsortiumCore progress callback", () => {
  it("reports progress for each probe in serial mode with role names", async () => {
    const onProgress = vi.fn();
    const callFn: ModelCallFn = async () => "WARN OK";
    const core = new ConsortiumCore(baseConfig, callFn);
    await core.deliberate("Test input", undefined, onProgress);

    // Serial: probe calls include role names
    expect(onProgress).toHaveBeenCalledWith("probe", 1, 2, "clarifier");
    expect(onProgress).toHaveBeenCalledWith("probe", 2, 2, "contrarian");
    expect(onProgress).toHaveBeenCalledWith("synthesis", 0, 1);
    expect(onProgress).toHaveBeenCalledWith("complete", 0, 0);
    expect(onProgress).toHaveBeenCalledTimes(4);
  });

  it("reports progress for parallel probes with role names", async () => {
    const onProgress = vi.fn();
    const callFn: ModelCallFn = async () => {
      await new Promise((r) => setTimeout(r, 30));
      return "WARN OK";
    };
    const config: ConsortiumConfig = { ...baseConfig, executionMode: "parallel" };
    const core = new ConsortiumCore(config, callFn);
    await core.deliberate("Test input", undefined, onProgress);

    expect(onProgress).toHaveBeenCalledWith("synthesis", 0, 1);
    expect(onProgress).toHaveBeenCalledWith("complete", 0, 0);
    // Two probe completions with role names (order may vary in parallel)
    const probeCalls = onProgress.mock.calls.filter((call) => call[0] === "probe");
    expect(probeCalls).toHaveLength(2);
    expect(probeCalls.some((c) => c[3] === "clarifier")).toBe(true);
    expect(probeCalls.some((c) => c[3] === "contrarian")).toBe(true);
  });

  it("skips progress callback when not provided", async () => {
    // No crash when onProgress is undefined
    const callFn: ModelCallFn = async () => "WARN OK";
    const core = new ConsortiumCore(baseConfig, callFn);
    const result = await core.deliberate("Test input");
    expect(result.synthesis).toBeDefined();
  });

  it("reports progress even when probes error", async () => {
    const onProgress = vi.fn();
    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "probe:0") {
        throw new Error("Network error");
      }
      return "WARN OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);
    await core.deliberate("Test input", undefined, onProgress);

    // Should still report progress for errored probe
    expect(onProgress).toHaveBeenCalledWith("probe", 1, 2, "clarifier");
    expect(onProgress).toHaveBeenCalledWith("probe", 2, 2, "contrarian");
  });

  it("reports no_contribution skip when all probes return NO_CONTRIBUTION", async () => {
    const onProgress = vi.fn();
    const callFn: ModelCallFn = async () => "NO_CONTRIBUTION";
    const core = new ConsortiumCore(baseConfig, callFn);
    await core.deliberate("Test input", undefined, onProgress);

    expect(onProgress).toHaveBeenCalledWith("probe", 1, 2, "clarifier");
    expect(onProgress).toHaveBeenCalledWith("probe", 2, 2, "contrarian");
    // Synthesis is skipped when all NO_CONTRIBUTION
    expect(onProgress).not.toHaveBeenCalledWith("synthesis", 0, 1);
    expect(onProgress).toHaveBeenCalledWith("complete", 0, 0);
  });
});